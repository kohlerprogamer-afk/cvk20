import { useState } from 'react';
import WeatherCard from './components/WeatherCard.jsx';
import ScheduleCard from './components/ScheduleCard.jsx';
import EmailsCard from './components/EmailsCard.jsx';
import NewsCard from './components/NewsCard.jsx';

const STAGES = [
  'Fetching weather...',
  'Fetching news...',
  'Building your brief...',
];

export default function App() {
  const [topic, setTopic] = useState('St. Louis Cardinals');
  const [loading, setLoading] = useState(false);
  const [stageIndex, setStageIndex] = useState(0);
  const [brief, setBrief] = useState(null);
  const [error, setError] = useState(null);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    setBrief(null);
    setStageIndex(0);

    const stageTimer = setInterval(() => {
      setStageIndex(i => Math.min(i + 1, STAGES.length - 1));
    }, 3500);

    try {
      // Step 1: fetch weather
      const weatherRes = await fetch('/api/weather');
      const weatherData = weatherRes.ok ? await weatherRes.json() : null;

      setStageIndex(1);

      // Step 2: generate brief
      const briefRes = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, weatherData }),
      });

      const payload = await briefRes.json();

      if (!briefRes.ok) throw new Error(payload.error || 'Failed to generate brief.');

      setBrief(payload.brief);
    } catch (err) {
      setError(err.message);
    } finally {
      clearInterval(stageTimer);
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-3xl mx-auto px-4 py-10">
        {/* Header */}
        <header className="mb-10">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-100">
            Morning Brief
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            {new Date().toLocaleDateString('en-US', {
              weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
              timeZone: 'America/Chicago',
            })}
          </p>
        </header>

        {/* Controls */}
        <div className="flex gap-3 mb-10">
          <input
            type="text"
            value={topic}
            onChange={e => setTopic(e.target.value)}
            placeholder="News topic..."
            disabled={loading}
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-600 focus:ring-1 focus:ring-zinc-600 disabled:opacity-50 transition"
          />
          <button
            onClick={handleGenerate}
            disabled={loading || !topic.trim()}
            className="bg-zinc-100 hover:bg-white text-zinc-900 font-medium text-sm px-5 py-2.5 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {loading ? 'Generating...' : 'Generate Brief'}
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20 gap-5">
            <div className="flex gap-1.5">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className="w-2 h-2 bg-zinc-400 rounded-full animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
            <p className="text-sm text-zinc-500">{STAGES[stageIndex]}</p>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="bg-red-950/50 border border-red-900 rounded-lg p-4 text-sm text-red-300">
            <span className="font-medium">Error:</span> {error}
          </div>
        )}

        {/* Raw fallback */}
        {brief?.raw && !loading && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <p className="text-xs text-zinc-500 mb-3 font-medium uppercase tracking-wider">
              Raw Response
            </p>
            <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-mono leading-relaxed">
              {brief.raw}
            </pre>
          </div>
        )}

        {/* Brief sections */}
        {brief && !brief.raw && !loading && (
          <div className="space-y-4">
            {/* Greeting */}
            <p className="text-lg font-medium text-zinc-100 pb-2">{brief.greeting}</p>

            <WeatherCard weather={brief.weather} />
            <ScheduleCard schedule={brief.schedule} />
            <EmailsCard emails={brief.emails} />
            <NewsCard news={brief.news} topic={brief.newsTopic} />
          </div>
        )}

        {/* Empty state */}
        {!brief && !loading && !error && (
          <div className="text-center py-20">
            <p className="text-zinc-600 text-sm">
              Enter a news topic and click Generate Brief to get started.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
