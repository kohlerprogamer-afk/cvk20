import express from 'express';
import cors from 'cors';
import { GoogleGenerativeAI } from '@google/generative-ai';
import { google } from 'googleapis';
import { XMLParser } from 'fast-xml-parser';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

dotenv.config();

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(cors());
app.use(express.json());

const STL_LAT = 38.627;
const STL_LON = -90.1994;

// ── Data fetchers ────────────────────────────────────────────────────────────

async function fetchWeather() {
  const url =
    `https://api.open-meteo.com/v1/forecast` +
    `?latitude=${STL_LAT}&longitude=${STL_LON}` +
    `&current=temperature_2m,apparent_temperature,weathercode,windspeed_10m,precipitation` +
    `&daily=temperature_2m_max,temperature_2m_min,weathercode` +
    `&temperature_unit=fahrenheit&windspeed_unit=mph` +
    `&timezone=America%2FChicago&forecast_days=1`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Weather API ${res.status}`);
  return res.json();
}

function weatherCodeDesc(code) {
  const map = {
    0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Icy fog',
    51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
    61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
    71: 'Light snow', 73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains',
    80: 'Light showers', 81: 'Showers', 82: 'Heavy showers',
    95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Heavy thunderstorm',
  };
  return map[code] ?? 'Unknown conditions';
}

async function fetchGmailEmails(token) {
  if (!token) return null;
  const auth = new google.auth.OAuth2();
  auth.setCredentials({ access_token: token });
  const gmail = google.gmail({ version: 'v1', auth });

  const list = await gmail.users.messages.list({
    userId: 'me',
    q: 'is:unread',
    maxResults: 5,
  });

  if (!list.data.messages?.length) return [];

  const messages = await Promise.all(
    list.data.messages.map(m =>
      gmail.users.messages.get({
        userId: 'me',
        id: m.id,
        format: 'metadata',
        metadataHeaders: ['Subject', 'From'],
      })
    )
  );

  return messages.map(m => {
    const headers = m.data.payload?.headers ?? [];
    const h = name => headers.find(x => x.name === name)?.value ?? '';
    return { subject: h('Subject'), from: h('From'), snippet: m.data.snippet ?? '' };
  });
}

async function fetchCalendarEvents(token) {
  if (!token) return null;
  const auth = new google.auth.OAuth2();
  auth.setCredentials({ access_token: token });
  const cal = google.calendar({ version: 'v3', auth });

  const now = new Date();
  const tz = 'America/Chicago';
  const startOfDay = new Date(now.toLocaleDateString('en-CA', { timeZone: tz })).toISOString();
  const endOfDay = new Date(
    new Date(startOfDay).getTime() + 86400000 - 1
  ).toISOString();

  const res = await cal.events.list({
    calendarId: 'primary',
    timeMin: startOfDay,
    timeMax: endOfDay,
    singleEvents: true,
    orderBy: 'startTime',
    timeZone: tz,
  });

  return (res.data.items ?? []).map(e => ({
    title: e.summary ?? 'Untitled',
    start: e.start?.dateTime ?? e.start?.date ?? '',
    end: e.end?.dateTime ?? e.end?.date ?? '',
    location: e.location ?? '',
  }));
}

async function fetchNewsRSS(topic) {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(topic)}&hl=en-US&gl=US&ceid=US:en`;
  const res = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
  if (!res.ok) throw new Error(`News RSS ${res.status}`);
  const xml = await res.text();
  const parser = new XMLParser({ ignoreAttributes: false });
  const doc = parser.parse(xml);
  const items = doc?.rss?.channel?.item ?? [];
  const arr = Array.isArray(items) ? items : [items];
  return arr.slice(0, 8).map(i => ({
    title: typeof i.title === 'string' ? i.title : (i.title?.['#text'] ?? ''),
    description: typeof i.description === 'string' ? i.description : '',
  }));
}

// ── Routes ───────────────────────────────────────────────────────────────────

app.get('/api/weather', async (_req, res) => {
  try {
    res.json(await fetchWeather());
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/generate', async (req, res) => {
  if (!process.env.GEMINI_API_KEY) {
    return res.status(500).json({ error: 'GEMINI_API_KEY is not set.' });
  }

  const { topic = 'St. Louis Cardinals', weatherData } = req.body;

  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    timeZone: 'America/Chicago',
  });

  // Parallel data fetching
  const gmailToken = process.env.GMAIL_TOKEN;
  const calendarToken = process.env.CALENDAR_TOKEN || process.env.GMAIL_TOKEN;

  const [emails, events, newsItems] = await Promise.allSettled([
    fetchGmailEmails(gmailToken),
    fetchCalendarEvents(calendarToken),
    fetchNewsRSS(topic),
  ]);

  const emailData = emails.status === 'fulfilled' ? emails.value : null;
  const eventData = events.status === 'fulfilled' ? events.value : null;
  const newsData = newsItems.status === 'fulfilled' ? newsItems.value : [];

  if (emails.status === 'rejected') console.error('Gmail error:', emails.reason.message);
  if (events.status === 'rejected') console.error('Calendar error:', events.reason.message);
  if (newsItems.status === 'rejected') console.error('News error:', newsItems.reason.message);

  // Build weather context from pre-fetched data
  let weatherContext = 'Weather data unavailable.';
  if (weatherData?.current) {
    const c = weatherData.current;
    const d = weatherData.daily;
    weatherContext =
      `${weatherCodeDesc(c.weathercode)}, ${c.temperature_2m}°F ` +
      `(feels like ${c.apparent_temperature}°F), wind ${c.windspeed_10m} mph. ` +
      `High: ${d?.temperature_2m_max?.[0]}°F, Low: ${d?.temperature_2m_min?.[0]}°F.`;
  }

  // Format data for prompt
  const emailSection = emailData === null
    ? 'Gmail not connected (GMAIL_TOKEN not set).'
    : emailData.length === 0
      ? 'No unread emails.'
      : emailData.map((e, i) =>
          `${i + 1}. From: ${e.from}\n   Subject: ${e.subject}\n   Preview: ${e.snippet}`
        ).join('\n');

  const calendarSection = eventData === null
    ? 'Google Calendar not connected (GMAIL_TOKEN not set).'
    : eventData.length === 0
      ? 'No events today.'
      : eventData.map(e => {
          const start = e.start ? new Date(e.start).toLocaleTimeString('en-US', {
            hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago',
          }) : '';
          return `- ${start ? start + ' — ' : ''}${e.title}${e.location ? ' @ ' + e.location : ''}`;
        }).join('\n');

  const newsSection = newsData.length === 0
    ? 'No news found.'
    : newsData.map((n, i) => `${i + 1}. ${n.title}`).join('\n');

  const prompt = `Today is ${today}. You are writing a concise morning brief. Use the data below and return ONLY a valid JSON object — no markdown fences, no extra text.

=== WEATHER (St. Louis, MO) ===
${weatherContext}

=== TODAY'S CALENDAR EVENTS ===
${calendarSection}

=== UNREAD EMAILS (5 most recent) ===
${emailSection}

=== NEWS HEADLINES (topic: "${topic}") ===
${newsSection}

Return this exact JSON structure:
{
  "greeting": "Good morning! Today is ${today}.",
  "weather": {
    "summary": "One-sentence weather summary",
    "current": "Current temp and feels-like e.g. 72°F (feels like 69°F)",
    "high": "e.g. 80°F",
    "low": "e.g. 60°F",
    "wind": "e.g. 12 mph"
  },
  "schedule": [
    { "time": "9:00 AM", "title": "Event title", "description": "" }
  ],
  "emails": [
    { "subject": "Subject", "from": "Sender", "summary": "What it's about and any action needed", "urgent": false }
  ],
  "news": [
    "Concise bullet point summarizing headline 1",
    "Concise bullet point summarizing headline 2",
    "Concise bullet point summarizing headline 3"
  ],
  "newsTopic": "${topic}"
}

Rules:
- schedule: if no events, use [{ "time": "", "title": "No events today", "description": "" }]
- emails: if not connected, use [{ "subject": "Gmail not connected", "from": "System", "summary": "Set GMAIL_TOKEN in .env to enable.", "urgent": false }]
- news: provide 3-5 bullet points synthesizing the headlines above
- urgent: true only if the email looks time-sensitive or action-required
- Respond with ONLY the JSON object.`;

  try {
    const genai = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
    const model = genai.getGenerativeModel({
      model: 'gemini-2.0-flash',
      generationConfig: { responseMimeType: 'application/json' },
    });
    const result = await model.generateContent(prompt);
    const text = result.response.text().trim();

    let brief;
    try {
      brief = JSON.parse(text);
    } catch {
      brief = { raw: text };
    }

    res.json({ brief });
  } catch (err) {
    console.error('Gemini error:', err);
    res.status(500).json({ error: err.message || 'Failed to generate brief.' });
  }
});

app.use(express.static(join(__dirname, 'dist')));
app.get('*', (_req, res) => res.sendFile(join(__dirname, 'dist', 'index.html')));

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));
