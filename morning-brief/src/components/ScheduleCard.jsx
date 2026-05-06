export default function ScheduleCard({ schedule }) {
  if (!schedule?.length) return null;

  return (
    <section className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
      <div className="border-l-2 border-emerald-500 pl-4 pr-5 py-4">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-emerald-500 mb-3">
          Today's Schedule
        </h2>
        <ul className="space-y-3">
          {schedule.map((event, i) => (
            <li key={i} className="flex gap-4">
              <span className="text-sm text-zinc-500 w-20 shrink-0 pt-0.5">
                {event.time || '—'}
              </span>
              <div>
                <p className="text-sm text-zinc-200 font-medium">{event.title}</p>
                {event.description && (
                  <p className="text-xs text-zinc-500 mt-0.5">{event.description}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
