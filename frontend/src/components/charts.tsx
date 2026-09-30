import TableChartOutlined from "@mui/icons-material/TableChartOutlined";
import InsertChartOutlined from "@mui/icons-material/InsertChartOutlined";
import {
  Box,
  Card,
  CardContent,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip as MuiTooltip,
  Typography,
} from "@mui/material";
import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART, SERIES } from "../lib/chartTheme";

/** A card holding one chart, with a chart/table toggle so no value is reachable only by hover. */
export function ChartCard({
  title,
  subtitle,
  table,
  children,
  legend,
}: {
  title: string;
  subtitle?: string;
  table: { columns: string[]; rows: (string | number)[][] };
  children: ReactNode;
  legend?: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", mb: 1 }}>
          <Box>
            <Typography variant="h4" component="h2">{title}</Typography>
            {subtitle && <Typography variant="caption" color="text.secondary">{subtitle}</Typography>}
          </Box>
          <MuiTooltip title={asTable ? "Show chart" : "Show as table"}>
            <IconButton size="small" onClick={() => setAsTable((v) => !v)} aria-label={asTable ? "Show chart" : "Show as table"}>
              {asTable ? <InsertChartOutlined fontSize="small" /> : <TableChartOutlined fontSize="small" />}
            </IconButton>
          </MuiTooltip>
        </Stack>
        {!asTable && legend}
        {asTable ? (
          <Table size="small">
            <TableHead>
              <TableRow>{table.columns.map((c) => <TableCell key={c}>{c}</TableCell>)}</TableRow>
            </TableHead>
            <TableBody>
              {table.rows.map((r, i) => (
                <TableRow key={i}>
                  {r.map((v, j) => (
                    <TableCell key={j} sx={j > 0 ? { fontVariantNumeric: "tabular-nums" } : undefined}>{v}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <Stack direction="row" spacing={2} sx={{ mb: 1 }} role="list" aria-label="Legend">
      {items.map((i) => (
        <Stack key={i.label} direction="row" spacing={0.75} sx={{ alignItems: "center" }} role="listitem">
          <Box sx={{ width: 14, height: 2, bgcolor: i.color, borderRadius: 1 }} />
          <Typography variant="caption" color="text.secondary">{i.label}</Typography>
        </Stack>
      ))}
    </Stack>
  );
}

const axisProps = {
  tick: { fill: CHART.inkMuted, fontSize: 12 },
  axisLine: { stroke: CHART.axis },
  tickLine: false,
} as const;

function ChartTooltipBox({ title, rows }: { title: string; rows: { label: string; value: string | number; color?: string }[] }) {
  return (
    <Box sx={{ bgcolor: "background.paper", border: 1, borderColor: "divider", borderRadius: 1, px: 1.5, py: 1, boxShadow: 2 }}>
      <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>{title}</Typography>
      {rows.map((r) => (
        <Stack key={r.label} direction="row" spacing={1} sx={{ alignItems: "center" }}>
          {r.color && <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: r.color }} />}
          <Typography variant="caption" color="text.secondary">{r.label}</Typography>
          <Typography variant="caption" sx={{ fontWeight: 600, ml: "auto", pl: 2 }}>{r.value}</Typography>
        </Stack>
      ))}
    </Box>
  );
}

interface SeriesDef {
  key: string;
  label: string;
}

/** Multi-series trend: 2px lines, crosshair tooltip, end labels (legend carries identity). */
export function TrendLines({ data, xKey, series, xFormat }: { data: Record<string, string | number>[]; xKey: string; series: SeriesDef[]; xFormat: (v: string) => string }) {
  const last = data.length - 1;
  return (
    <Box sx={{ height: 260 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 40, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={CHART.grid} />
          <XAxis dataKey={xKey} tickFormatter={xFormat} {...axisProps} minTickGap={24} />
          <YAxis allowDecimals={false} {...axisProps} axisLine={false} width={40} />
          <Tooltip
            cursor={{ stroke: CHART.axis, strokeWidth: 1 }}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <ChartTooltipBox
                  title={xFormat(String(label))}
                  rows={series.map((s, i) => ({ label: s.label, value: Number(payload.find((p) => p.dataKey === s.key)?.value ?? 0), color: SERIES[i] }))}
                />
              ) : null
            }
          />
          {series.map((s, i) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={SERIES[i]}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              dot={false}
              activeDot={{ r: 5, stroke: CHART.surface, strokeWidth: 2 }}
              isAnimationActive={false}
            >
              <LabelList
                dataKey={s.key}
                content={({ x, y, value, index }) =>
                  index === last ? (
                    <text x={Number(x) + 8} y={Number(y) + 4} fontSize={12} fill={CHART.inkSecondary}>{value}</text>
                  ) : null
                }
              />
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Box>
  );
}

/** Single-series horizontal bars: one hue, rounded data-end, value at the tip. */
export function BarList({ data, valueLabel }: { data: { name: string; value: number }[]; valueLabel: string }) {
  const height = Math.max(120, data.length * 34 + 16);
  return (
    <Box sx={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 36, bottom: 0, left: 0 }} barCategoryGap={8}>
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis type="category" dataKey="name" width={150} {...axisProps} axisLine={false} interval={0} />
          <Tooltip
            cursor={{ fill: "#f3f4f6" }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <ChartTooltipBox title={String(payload[0].payload.name)} rows={[{ label: valueLabel, value: Number(payload[0].value) }]} />
              ) : null
            }
          />
          <Bar dataKey="value" fill={SERIES[0]} barSize={CHART.barSize} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            <LabelList dataKey="value" position="right" fill={CHART.inkSecondary} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}
