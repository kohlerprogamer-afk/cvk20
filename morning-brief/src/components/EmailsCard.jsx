export default function EmailsCard({ emails }) {
  if (!emails?.length) return null;

  return (
    <section className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="border-l-2 border-amber-500 pl-4 pr-5 py-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-amber-500 mb-3">
          Email Highlights
        </h2>
        <ul className="space-y-4">
          {emails.map((email, i) => (
            <li key={i} className="flex gap-3">
              {email.urgent && (
                <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0 self-start mt-1.5" />
              )}
              {!email.urgent && (
                <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-zinc-700 shrink-0 self-start mt-1.5" />
              )}
              <div className="min-w-0">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <p className="text-sm text-zinc-200 font-medium truncate">{email.subject}</p>
                  {email.urgent && (
                    <span className="text-xs text-amber-400 font-medium shrink-0">urgent</span>
                  )}
                </div>
                <p className="text-xs text-zinc-500 mt-0.5">{email.from}</p>
                <p className="text-sm text-zinc-400 mt-1">{email.summary}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
