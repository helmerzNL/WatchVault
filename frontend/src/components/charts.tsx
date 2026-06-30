import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { useMemo } from "react";

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

const grid = () => cssVar("--hairline", "rgba(0,0,0,0.1)");
const axis = () => cssVar("--text-tertiary", "#8e8e93");
const accent = () => cssVar("--accent", "#0a84ff");

const tooltipStyle = {
  background: "var(--surface-strong)",
  border: "1px solid var(--hairline-strong)",
  borderRadius: 12,
  color: "var(--text)",
  fontSize: 13,
  boxShadow: "var(--shadow)",
  backdropFilter: "blur(12px)",
};

interface SeriesPoint { label: string; value: number; }

// Round up to a clean axis bound for tidy ticks without excessive empty space.
function niceMax(v: number): number {
  if (!(v > 0)) return 1;
  const exp = Math.floor(Math.log10(v));
  const base = Math.pow(10, exp);
  const f = v / base;
  const steps = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
  const nice = steps.find((s) => f <= s + 1e-9) ?? 10;
  return nice * base;
}

export function TrendArea({ data, height = 240 }: { data: SeriesPoint[]; height?: number }) {
  // Explicit y-max with guaranteed headroom. `type="monotone"` can overshoot the
  // data max at the first/last point, so a fixed numeric domain (≥ max + 1 and
  // ~20% margin, rounded to a nice bound) keeps every peak in view across all
  // granularities — including a month-view spike sitting on the edge.
  const yMax = useMemo(() => {
    const max = Math.max(0, ...data.map((d) => d.value || 0));
    if (max <= 0) return 1;
    return Math.max(niceMax(max * 1.2), max + 1);
  }, [data]);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: -16 }}>
        <defs>
          <linearGradient id="wv-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent()} stopOpacity={0.45} />
            <stop offset="100%" stopColor={accent()} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={grid()} vertical={false} />
        <XAxis dataKey="label" stroke={axis()} tickLine={false} axisLine={false} fontSize={12} minTickGap={20} />
        <YAxis stroke={axis()} tickLine={false} axisLine={false} fontSize={12} width={42}
          domain={[0, yMax]} allowDataOverflow={false} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: accent(), strokeOpacity: 0.3 }} />
        <Area type="monotone" dataKey="value" stroke={accent()} strokeWidth={2.5} fill="url(#wv-area)" name="Hours" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function Spark({ data, height = 56 }: { data: SeriesPoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
        <Line type="monotone" dataKey="value" stroke={accent()} strokeWidth={2} dot={false} />
        <Tooltip contentStyle={tooltipStyle} />
      </LineChart>
    </ResponsiveContainer>
  );
}

interface StackRow { label: string; [series: string]: number | string; }

export function StackedBars({
  data, series, height = 300,
}: {
  data: StackRow[];
  series: { key: string; name: string; color: string }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={grid()} vertical={false} />
        <XAxis dataKey="label" stroke={axis()} tickLine={false} axisLine={false} fontSize={12} minTickGap={16} />
        <YAxis stroke={axis()} tickLine={false} axisLine={false} fontSize={12} width={42} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--accent-subtle)" }} />
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} stackId="a" fill={s.color || accent()}
            radius={i === series.length - 1 ? [4, 4, 0, 0] : undefined as any} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function HBars({
  data, height = 320,
}: {
  data: { label: string; value: number; color?: string }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart layout="vertical" data={data} margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid stroke={grid()} horizontal={false} />
        <XAxis type="number" stroke={axis()} tickLine={false} axisLine={false} fontSize={12} />
        <YAxis type="category" dataKey="label" stroke={axis()} tickLine={false} axisLine={false}
          fontSize={12} width={110} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--accent-subtle)" }} />
        <Bar dataKey="value" radius={[0, 6, 6, 0]} name="Hours">
          {data.map((d, i) => <Cell key={i} fill={d.color || accent()} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
