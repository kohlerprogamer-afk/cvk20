export default function NewsCard({ news, topic }) {
  if (!news?.length) return null;

  return (
    <section className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="border-l-2 border-violet-500 pl-4 pr-5 py-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-violet-500 mb-1">
          News Digest
        </h2>
        {topic && (
          <p className="text-xs text-zinc-600 mb-3">{topic}</p>
        )}
        <ul className="space-y-2.5">
          {news.map((item, i) => (
            <li key={i} className="flex gap-3">
              <span className="text-zinc-600 text-sm shrink-0 pt-0.5">·</span>
              <p className="text-sm text-zinc-300 leading-relaxed">{item}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
