import { useMemo } from "react";
import { localeTag } from "../lib/format";

interface Day { date: string; count: number; hours: number; }

// GitHub-style calendar heatmap. Columns = weeks, rows = weekdays.
export function Heatmap({ days, year, selected, onSelect }: {
  days: Day[]; year: number; selected?: string | null; onSelect?: (date: string) => void;
}) {
  const { cells, max, months, cols } = useMemo(() => {
    const byDate = new Map(days.map((d) => [d.date, d]));
    const start = new Date(Date.UTC(year, 0, 1));
    const end = new Date(Date.UTC(year, 11, 31));
    // pad to start on Sunday
    const startPad = start.getUTCDay();
    const cur = new Date(start);
    cur.setUTCDate(cur.getUTCDate() - startPad);

    const cells: { date: string | null; count: number; hours: number }[] = [];
    let max = 0;
    const months: { col: number; label: string }[] = [];
    let col = 0;
    let lastMonth = -1;

    while (cur <= end || cur.getUTCDay() !== 0) {
      const inYear = cur.getUTCFullYear() === year;
      const iso = cur.toISOString().slice(0, 10);
      const rec = inYear ? byDate.get(iso) : undefined;
      const count = rec?.count || 0;
      if (count > max) max = count;
      if (cur.getUTCDay() === 0) {
        const m = cur.getUTCMonth();
        if (inYear && m !== lastMonth) {
          months.push({ col, label: new Date(Date.UTC(year, m, 1)).toLocaleDateString(localeTag(), { month: "short" }) });
          lastMonth = m;
        }
        col++;
      }
      cells.push({ date: inYear ? iso : null, count, hours: rec?.hours || 0 });
      cur.setUTCDate(cur.getUTCDate() + 1);
      if (cur > end && cur.getUTCDay() === 0) break;
    }
    return { cells, max, months, cols: col };
  }, [days, year]);

  const level = (c: number) => {
    if (!c || max === 0) return 0;
    const r = c / max;
    if (r > 0.66) return 1;
    if (r > 0.33) return 0.7;
    return 0.4;
  };

  return (
    <div>
      <div className="heatmap-scroll">
        <div className="heatmap-months" style={{ gridTemplateColumns: `repeat(${cols}, 13px)` }}>
          {months.map((m, i) => (
            <span key={i} style={{ gridColumn: `${m.col + 1} / ${(months[i + 1]?.col ?? cols) + 1}` }}>{m.label}</span>
          ))}
        </div>
        <div className="heatmap">
          {cells.map((c, i) => {
            const clickable = !!(c.date && c.count && onSelect);
            const isSel = !!(c.date && selected && c.date === selected);
            return (
              <div
                key={i}
                className={"cell" + (clickable ? " clickable" : "") + (isSel ? " selected" : "")}
                onClick={clickable ? () => onSelect!(c.date!) : undefined}
                title={c.date ? `${c.date}: ${c.count} watched · ${c.hours}h` : ""}
                style={{
                  background: c.date
                    ? c.count
                      ? `color-mix(in srgb, var(--accent) ${level(c.count) * 100}%, transparent)`
                      : "var(--accent-subtle)"
                    : "transparent",
                  cursor: clickable ? "pointer" : "default",
                }}
              />
            );
          })}
        </div>
      </div>
      <div className="heat-legend" style={{ marginTop: 8 }}>
        <span>Less</span>
        <span className="cell" style={{ background: "var(--accent-subtle)" }} />
        <span className="cell" style={{ background: "color-mix(in srgb, var(--accent) 40%, transparent)" }} />
        <span className="cell" style={{ background: "color-mix(in srgb, var(--accent) 70%, transparent)" }} />
        <span className="cell" style={{ background: "var(--accent)" }} />
        <span>More</span>
      </div>
    </div>
  );
}
