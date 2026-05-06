import express from 'express';
import cors from 'cors';
import { XMLParser } from 'fast-xml-parser';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(cors());
app.use(express.json());

const STL_LAT = 38.627;
const STL_LON = -90.1994;

const WEATHER_CODES = {
  0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
  45: 'Fog', 48: 'Icy fog',
  51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
  61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
  71: 'Light snow', 73: 'Snow', 75: 'Heavy snow', 77: 'Snow grains',
  80: 'Light showers', 81: 'Showers', 82: 'Heavy showers',
  95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Heavy thunderstorm',
};

async function fetchWeather() {
  const url =
    `https://api.open-meteo.com/v1/forecast` +
    `?latitude=${STL_LAT}&longitude=${STL_LON}` +
    `&current=temperature_2m,apparent_temperature,weathercode,windspeed_10m` +
    `&daily=temperature_2m_max,temperature_2m_min` +
    `&temperature_unit=fahrenheit&windspeed_unit=mph` +
    `&timezone=America%2FChicago&forecast_days=1`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Weather API ${res.status}`);
  return res.json();
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
  return arr.slice(0, 5).map(i => {
    const raw = typeof i.title === 'string' ? i.title : (i.title?.['#text'] ?? '');
    // Strip trailing publisher attribution (e.g. " - ESPN")
    return raw.replace(/\s[-–]\s[^-–]+$/, '').trim();
  }).filter(Boolean);
}

app.get('/api/weather', async (_req, res) => {
  try {
    res.json(await fetchWeather());
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/generate', async (req, res) => {
  const { topic = 'St. Louis Cardinals', weatherData } = req.body;

  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    timeZone: 'America/Chicago',
  });

  // Fetch news (weather already fetched by frontend and passed in)
  let news = [];
  try {
    news = await fetchNewsRSS(topic);
  } catch (err) {
    console.error('News RSS error:', err.message);
  }

  // Format weather
  let weather = {
    summary: 'Weather data unavailable.',
    current: '—', high: '—', low: '—', wind: '—',
  };
  if (weatherData?.current) {
    const c = weatherData.current;
    const d = weatherData.daily;
    const condition = WEATHER_CODES[c.weathercode] ?? 'Unknown';
    const high = d?.temperature_2m_max?.[0];
    const low = d?.temperature_2m_min?.[0];
    weather = {
      summary: `${condition} in St. Louis today with a high of ${high}°F.`,
      current: `${c.temperature_2m}°F (feels like ${c.apparent_temperature}°F)`,
      high: `${high}°F`,
      low: `${low}°F`,
      wind: `${c.windspeed_10m} mph`,
    };
  }

  const brief = {
    greeting: `Good morning! Today is ${today}.`,
    weather,
    schedule: [
      { time: '', title: 'Calendar not connected', description: 'No setup required — this section is always optional.' },
    ],
    emails: [
      { subject: 'Email not connected', from: 'System', summary: 'No setup required — this section is always optional.', urgent: false },
    ],
    news: news.length > 0 ? news : ['No news found for this topic.'],
    newsTopic: topic,
  };

  res.json({ brief });
});

app.use(express.static(join(__dirname, 'dist')));
app.get('*', (_req, res) => res.sendFile(join(__dirname, 'dist', 'index.html')));

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));
