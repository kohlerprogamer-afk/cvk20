import express from 'express';
import cors from 'cors';
import Anthropic from '@anthropic-ai/sdk';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

dotenv.config();

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(cors());
app.use(express.json());

// St. Louis, MO coordinates
const STL_LAT = 38.627;
const STL_LON = -90.1994;

app.get('/api/weather', async (req, res) => {
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${STL_LAT}&longitude=${STL_LON}&current=temperature_2m,apparent_temperature,weathercode,windspeed_10m,precipitation&daily=temperature_2m_max,temperature_2m_min,weathercode&temperature_unit=fahrenheit&windspeed_unit=mph&timezone=America%2FChicago&forecast_days=1`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Weather API error: ${response.status}`);
    const data = await response.json();
    res.json(data);
  } catch (err) {
    console.error('Weather fetch error:', err);
    res.status(500).json({ error: err.message });
  }
});

function describeWeatherCode(code) {
  const codes = {
    0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Foggy', 48: 'Icy fog',
    51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
    61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
    71: 'Light snow', 73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains',
    80: 'Light showers', 81: 'Showers', 82: 'Heavy showers',
    85: 'Snow showers', 86: 'Heavy snow showers',
    95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Thunderstorm with heavy hail',
  };
  return codes[code] ?? 'Unknown';
}

app.post('/api/generate', async (req, res) => {
  const { topic = 'St. Louis Cardinals', weatherData } = req.body;

  if (!process.env.ANTHROPIC_API_KEY) {
    return res.status(500).json({ error: 'ANTHROPIC_API_KEY is not set.' });
  }

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    timeZone: 'America/Chicago',
  });

  let weatherContext = 'Weather data unavailable.';
  if (weatherData?.current) {
    const c = weatherData.current;
    const d = weatherData.daily;
    const condition = describeWeatherCode(c.weathercode);
    weatherContext = `${condition}, ${c.temperature_2m}°F (feels like ${c.apparent_temperature}°F), wind ${c.windspeed_10m} mph. High: ${d?.temperature_2m_max?.[0]}°F, Low: ${d?.temperature_2m_min?.[0]}°F.`;
  }

  const gmailToken = process.env.GMAIL_TOKEN;
  const calendarToken = process.env.CALENDAR_TOKEN || process.env.GMAIL_TOKEN;

  const mcpServers = [];
  if (gmailToken) {
    mcpServers.push({
      type: 'url',
      url: 'https://gmailmcp.googleapis.com/mcp/v1',
      name: 'gmail',
      authorization_token: gmailToken,
    });
  }
  if (calendarToken) {
    mcpServers.push({
      type: 'url',
      url: 'https://calendarmcp.googleapis.com/mcp/v1',
      name: 'gcalendar',
      authorization_token: calendarToken,
    });
  }

  const hasGmail = mcpServers.some(s => s.name === 'gmail');
  const hasCalendar = mcpServers.some(s => s.name === 'gcalendar');

  const systemPrompt = `You are a morning brief assistant. Today is ${today}. Your job is to compile a concise, useful morning briefing using the tools available to you.

After gathering all information, respond with ONLY a valid JSON object — no markdown fences, no extra text — using this exact structure:
{
  "greeting": "Good morning! Today is ${today}.",
  "weather": {
    "summary": "One-sentence weather summary",
    "current": "Current temp and feels-like",
    "high": "Today's high",
    "low": "Today's low",
    "wind": "Wind description"
  },
  "schedule": [
    { "time": "9:00 AM", "title": "Event title", "description": "Optional details or empty string" }
  ],
  "emails": [
    { "subject": "Subject line", "from": "Sender name or email", "summary": "What this is about and any action needed", "urgent": false }
  ],
  "news": [
    "Bullet point 1",
    "Bullet point 2",
    "Bullet point 3"
  ],
  "newsTopic": "${topic}"
}

Rules:
- schedule: if no calendar access or no events, use [{ "time": "", "title": "No events today", "description": "" }]
- emails: if no Gmail access, use [{ "subject": "Gmail not connected", "from": "System", "summary": "Set GMAIL_TOKEN in .env to enable email summaries.", "urgent": false }]
- news: always provide 3-5 bullet points from your web search
- Respond with ONLY the JSON object.`;

  const userMessage = `Please create my morning brief for today (${today}).

Weather in St. Louis, MO: ${weatherContext}

${hasCalendar ? "Use your Google Calendar MCP tool to list today's events." : 'Google Calendar is not connected.'}

${hasGmail ? 'Use your Gmail MCP tool to find the 5 most recent unread emails. Summarize each briefly.' : 'Gmail is not connected.'}

Use the web_search tool to find the latest news about: "${topic}". Summarize in 3-5 bullet points.

Return the complete brief as the JSON structure specified.`;

  try {
    const betas = ['web-search-2025-03-05'];
    if (mcpServers.length > 0) betas.push('mcp-client-2025-04-04');

    const requestParams = {
      model: 'claude-sonnet-4-20250514',
      max_tokens: 4096,
      system: systemPrompt,
      messages: [{ role: 'user', content: userMessage }],
      tools: [{ type: 'web_search_20250305', name: 'web_search' }],
    };

    if (mcpServers.length > 0) {
      requestParams.mcp_servers = mcpServers;
    }

    const response = await client.beta.messages.create({
      ...requestParams,
      betas,
    });

    const textContent = response.content.find(c => c.type === 'text');
    if (!textContent) throw new Error('No text in API response.');

    let brief;
    try {
      const raw = textContent.text.trim();
      const jsonStr = raw.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
      brief = JSON.parse(jsonStr);
    } catch {
      brief = { raw: textContent.text };
    }

    res.json({ brief });
  } catch (err) {
    console.error('Anthropic API error:', err);
    res.status(500).json({ error: err.message || 'Failed to generate brief.' });
  }
});

// Serve built frontend in production
app.use(express.static(join(__dirname, 'dist')));
app.get('*', (_req, res) => {
  res.sendFile(join(__dirname, 'dist', 'index.html'));
});

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));
