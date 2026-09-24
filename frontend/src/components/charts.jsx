// Dashboard figures and charts.
//
// Colour: every chart here is single-series, so marks use one validated hue -
// brand-600 (#4f46e5) on the white light card and brand-500 (#6366f1) on the
// slate-900 dark card. Both pass the lightness-band, chroma and >=3:1 contrast
// checks against the surface they render on. Text never wears the data colour.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Table2, BarChart3 } from 'lucide-react'
import { formatCount } from '../lib/format'

const MARK_FILL = 'fill-brand-600 dark:fill-brand-500'
const MARK_BG = 'bg-brand-600 dark:bg-brand-500'

function useElementWidth() {
  const ref = useRef(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setWidth(el.getBoundingClientRect().width)
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}


// ------------------------------------------------------------------ figures

export function StatTile({ label, value, sub, icon: Icon, status }) {
  // Status tiles (processing / failed) carry an icon + label; the number stays in ink.
  const statusStyle = {
    warning: 'text-amber-600 dark:text-amber-400',
    critical: 'text-red-600 dark:text-red-400',
    good: 'text-emerald-600 dark:text-emerald-400',
  }[status]
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-slate-500 dark:text-slate-400">{label}</p>
        {Icon && (
          <Icon
            className={`size-4 ${statusStyle || 'text-slate-400 dark:text-slate-500'}`}
            aria-hidden="true"
          />
        )}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
        {typeof value === 'number' ? formatCount(value) : value}
      </p>
      {sub && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{sub}</p>}
    </div>
  )
}

export function Meter({ label, value, caption }) {
  const pct = Math.max(0, Math.min(1, value || 0))
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <span className="text-sm text-slate-600 dark:text-slate-300">{label}</span>
        <span className="text-lg font-semibold text-slate-900 dark:text-white">
          {(pct * 100).toFixed(0)}%
        </span>
      </div>
      <div
        className="h-2.5 w-full overflow-hidden rounded-full bg-brand-100 dark:bg-brand-900/60"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct * 100)}
        aria-label={label}
      >
        <div className={`h-full rounded-full ${MARK_BG}`} style={{ width: `${pct * 100}%` }} />
      </div>
      {caption && <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{caption}</p>}
    </div>
  )
}

// ------------------------------------------------------------- chart frame

export function ChartCard({ title, subtitle, table, children, empty, emptyText }) {
  const [showTable, setShowTable] = useState(false)
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <header className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}
        </div>
        {table && !empty && (
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            aria-pressed={showTable}
          >
            {showTable ? <BarChart3 className="size-3.5" /> : <Table2 className="size-3.5" />}
            {showTable ? 'Chart' : 'Table'}
          </button>
        )}
      </header>
      {empty ? (
        <p className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">{emptyText || 'No data yet.'}</p>
      ) : showTable ? (
        table
      ) : (
        children
      )}
    </section>
  )
}

export function DataTable({ columns, rows }) {
  return (
    <div className="max-h-72 overflow-auto rounded-lg border border-slate-200 dark:border-slate-800">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`px-3 py-2 font-medium ${c.numeric ? 'text-right' : ''}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`px-3 py-1.5 text-slate-700 dark:text-slate-300 ${c.numeric ? 'text-right tabular-nums' : ''}`}
                >
                  {c.format ? c.format(row[c.key]) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --------------------------------------------------------- column chart

function niceTicks(max, count = 4) {
  if (max <= 0) return [0, 1]
  const raw = max / count
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) || raw
  const top = Math.ceil(max / step) * step
  const ticks = []
  for (let v = 0; v <= top + step / 2; v += step) ticks.push(Math.round(v * 1000) / 1000)
  return ticks
}

// Rounded top (the data end), square bottom (the baseline).
function columnPath(x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h)
  if (h <= 0) return ''
  return [
    `M${x},${y + h}`,
    `L${x},${y + radius}`,
    `Q${x},${y} ${x + radius},${y}`,
    `L${x + w - radius},${y}`,
    `Q${x + w},${y} ${x + w},${y + radius}`,
    `L${x + w},${y + h}`,
    'Z',
  ].join(' ')
}

export function ColumnChart({ data, valueLabel = 'Questions', formatLabel = (d) => d }) {
  const [wrapRef, width] = useElementWidth()
  const [active, setActive] = useState(null)
  const height = 200
  const margin = { top: 12, right: 8, bottom: 26, left: 32 }
  const plotW = Math.max(0, width - margin.left - margin.right)
  const plotH = height - margin.top - margin.bottom

  const max = Math.max(0, ...data.map((d) => d.value))
  const ticks = useMemo(() => niceTicks(max), [max])
  const top = ticks[ticks.length - 1] || 1
  const band = data.length ? plotW / data.length : 0
  const barW = Math.min(24, Math.max(2, band * 0.6))
  // Show only as many x labels as fit (~44px each).
  const labelEvery = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(plotW / 44))))

  const y = (v) => margin.top + plotH - (v / top) * plotH

  useEffect(() => {
    if (active !== null && active >= data.length) setActive(null)
  }, [active, data.length])

  const activeDatum = active !== null ? data[active] : null
  const tooltipLeft =
    activeDatum !== null && activeDatum !== undefined
      ? Math.min(Math.max(margin.left + band * active + band / 2, 60), Math.max(60, width - 60))
      : 0

  return (
    <div ref={wrapRef} className="relative w-full">
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`${valueLabel} per day`}>
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={margin.left}
                x2={width - margin.right}
                y1={y(t)}
                y2={y(t)}
                className={t === 0 ? 'stroke-slate-300 dark:stroke-slate-700' : 'stroke-slate-200 dark:stroke-slate-800'}
                strokeWidth={1}
                shapeRendering="crispEdges"
              />
              <text
                x={margin.left - 8}
                y={y(t)}
                dy="0.32em"
                textAnchor="end"
                className="fill-slate-500 text-[11px] tabular-nums dark:fill-slate-400"
              >
                {formatCount(t)}
              </text>
            </g>
          ))}

          {data.map((d, i) => {
            const x = margin.left + band * i + (band - barW) / 2
            const h = (d.value / top) * plotH
            const isActive = active === i
            return (
              <g key={d.key}>
                <path
                  d={columnPath(x, y(d.value), barW, h, 4)}
                  className={`${MARK_FILL} transition-opacity ${active !== null && !isActive ? 'opacity-60' : ''}`}
                />
                {i % labelEvery === 0 && (
                  <text
                    x={margin.left + band * i + band / 2}
                    y={height - 8}
                    textAnchor="middle"
                    className="fill-slate-500 text-[11px] dark:fill-slate-400"
                  >
                    {formatLabel(d.key)}
                  </text>
                )}
                {/* The whole band is the hit target, not just the painted column. */}
                <rect
                  x={margin.left + band * i}
                  y={margin.top}
                  width={band}
                  height={plotH}
                  fill="transparent"
                  tabIndex={0}
                  role="button"
                  aria-label={`${formatLabel(d.key)}: ${d.value} ${valueLabel.toLowerCase()}`}
                  onPointerEnter={() => setActive(i)}
                  onPointerLeave={() => setActive(null)}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                  className="cursor-default outline-none"
                />
              </g>
            )
          })}
        </svg>
      )}

      {activeDatum && (
        <div
          className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-800"
          style={{ left: tooltipLeft }}
          role="status"
        >
          <p className="text-base font-semibold text-slate-900 dark:text-white">{formatCount(activeDatum.value)}</p>
          <p className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
            <span className="inline-block h-0.5 w-3 rounded bg-brand-600 dark:bg-brand-500" aria-hidden="true" />
            {valueLabel} · {formatLabel(activeDatum.key)}
          </p>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------ horizontal bars

export function BarList({ data, unit = '' }) {
  const max = Math.max(1, ...data.map((d) => d.count))
  return (
    <ul className="space-y-3">
      {data.map((d) => (
        <li
          key={d.label}
          className="group"
          tabIndex={0}
          aria-label={`${d.label}: ${d.count}${unit ? ` ${unit}` : ''}`}
          title={`${d.label}: ${d.count}${unit ? ` ${unit}` : ''}`}
        >
          <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate text-slate-700 dark:text-slate-300">{d.label}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-2.5 flex-1">
              <div
                className={`h-full rounded-r-[4px] ${MARK_BG} transition-opacity group-hover:opacity-80 group-focus:opacity-80`}
                style={{ width: `${Math.max(2, (d.count / max) * 100)}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right text-sm font-medium tabular-nums text-slate-900 dark:text-white">
              {formatCount(d.count)}
            </span>
          </div>
        </li>
      ))}
    </ul>
  )
}
