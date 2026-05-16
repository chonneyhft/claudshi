import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";

type Props = {
  data: { value: number }[];
  positive?: boolean;
  height?: number;
};

export function Sparkline({ data, positive = true, height = 60 }: Props) {
  const color = positive ? "#3ecf8e" : "#f87171";
  const id = `spark-${positive ? "p" : "n"}`;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#${id})`}
          isAnimationActive
          animationDuration={800}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
