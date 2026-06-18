import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'
import { DIMENSIONS, BRAND, BRAND_FILL } from '../constants/labels'

// 用 factory + plotly.js-dist-min(而非默认的完整 plotly.js)接入,打包更友好、体积更小。
const Plot = createPlotlyComponent(Plotly)

// 5 维能力雷达图。数据从 props(dimAvg)进,组件本身无状态。
export default function RadarChart({ dimAvg }) {
  const vals = DIMENSIONS.map((d) => dimAvg?.[d.key] ?? 0) // 缺失维度按 0 处理(沿用原逻辑)
  const labels = DIMENSIONS.map((d) => d.short.replace(' ', '<br>')) // '<br>' 是 Plotly 的换行

  const data = [
    {
      type: 'scatterpolar',
      // 闭合多边形: 首元素再追加到末尾,折线才会收口。
      r: [...vals, vals[0]],
      theta: [...labels, labels[0]],
      fill: 'toself',
      line: { color: BRAND },
      fillcolor: BRAND_FILL,
      hovertemplate: '%{theta}: %{r}<extra></extra>',
    },
  ]
  const layout = {
    polar: { radialaxis: { visible: true, range: [0, 100] } }, // 固定 0–100,不自动缩放
    showlegend: false,
    height: 340,
    margin: { l: 60, r: 60, t: 30, b: 30 },
  }

  return (
    <Plot
      data={data}
      layout={layout}
      config={{ displayModeBar: false, responsive: true }}
      useResizeHandler
      style={{ width: '100%', height: '340px' }}
    />
  )
}
