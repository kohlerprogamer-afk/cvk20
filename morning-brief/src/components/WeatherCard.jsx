export default function WeatherCard({ weather }) {
  if (!weather) return null;

  return (
    <section className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="border-l-2 border-sky-500 pl-4 pr-5 py-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-sky-500 mb-3">
          Weather · St. Louis, MO
        </h2>
        <p className="text-base text-zinc-200 mb-3">{weather.summary}</p>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
          <div className="flex justify-between gap-2">
            <span className="text-zinc-500">Now</span>
            <span className="text-zinc-200">{weather.current}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-zinc-500">Wind</span>
            <span className="text-zinc-200">{weather.wind}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-zinc-500">High</span>
            <span className="text-zinc-200">{weather.high}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-zinc-500">Low</span>
            <span className="text-zinc-200">{weather.low}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
