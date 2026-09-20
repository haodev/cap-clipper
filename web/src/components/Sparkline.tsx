type Props = {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: string;
  /** Index to mark with a dot, usually the peak hour. */
  markIndex?: number;
};

/** 24-point hourly curve. Deliberately unlabelled - the Keepa-style card
 *  supplies the numbers, this only carries the shape. */
export default function Sparkline({
  values,
  width = 220,
  height = 44,
  stroke = "#38bdf8",
  fill = "rgba(56,189,248,0.16)",
  markIndex,
}: Props) {
  if (!values.length) return null;
  const max = Math.max(...values, 1);
  const stepX = width / Math.max(values.length - 1, 1);
  const y = (v: number) => height - (v / max) * (height - 4) - 2;
  const pts = values.map((v, i) => `${i * stepX},${y(v)}`);
  const line = `M ${pts.join(" L ")}`;
  const area = `${line} L ${width},${height} L 0,${height} Z`;

  return (
    <svg width={width} height={height} className="overflow-visible">
      <path d={area} fill={fill} />
      <path d={line} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" />
      {markIndex !== undefined && values[markIndex] !== undefined && (
        <circle cx={markIndex * stepX} cy={y(values[markIndex])} r={3} fill={stroke} />
      )}
    </svg>
  );
}
