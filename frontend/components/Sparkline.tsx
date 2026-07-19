import type { Direction } from "@/lib/format";

interface Props {
  data: number[];
  dir?: Direction;
  width?: number;
  height?: number;
  className?: string;
  label?: string;
}

/**
 * A tiny inline SVG trend line — no chart library, so it's cheap enough to render
 * one per board row. Colored by movement direction; a dashed baseline stands in
 * when there aren't enough points to draw a line.
 */
export function Sparkline({ data, dir = "flat", width = 104, height = 28, className = "", label }: Props) {
  const pad = 3;

  if (!data || data.length < 2) {
    return (
      <svg width={width} height={height} className={`text-muted ${className}`} aria-hidden="true">
        <line
          x1={pad}
          y1={height / 2}
          x2={width - pad}
          y2={height / 2}
          stroke="currentColor"
          strokeWidth="1"
          strokeDasharray="2 3"
          opacity="0.5"
        />
      </svg>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = (width - pad * 2) / (data.length - 1);
  const pts = data.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (1 - (v - min) / span) * (height - pad * 2);
    return [x, y] as const;
  });

  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const [lx, ly] = pts[pts.length - 1];
  const area = `${line} L${lx.toFixed(2)},${height} L${pts[0][0].toFixed(2)},${height} Z`;

  const color =
    dir === "up" ? "text-gain" : dir === "down" ? "text-loss" : "text-ink-soft";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`${color} ${className}`}
      role="img"
      aria-label={label ?? "30-day trend"}
    >
      <path d={area} fill="currentColor" opacity="0.09" />
      <path
        d={line}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lx} cy={ly} r="1.9" fill="currentColor" />
    </svg>
  );
}
