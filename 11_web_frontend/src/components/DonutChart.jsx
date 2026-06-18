import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'
import { SET2 } from '../constants/labels'

const Plot = createPlotlyComponent(Plotly)

// 甜甜圈图:展示这套约束用了哪些校验方式(verifier 类型分布)。数据从 props 进。
export default function DonutChart({ labels, values }) {
  const data = [
    {
      type: 'pie',
      labels,
      values,
      hole: 0.4,
      marker: { colors: SET2 },
      textinfo: 'label+percent',
      textposition: 'inside',
      hovertemplate: '%{label}: %{value} (%{percent})<extra></extra>',
    },
  ]
  const layout = { height: 280, margin: { l: 10, r: 10, t: 10, b: 10 } }

  return (
    <Plot
      data={data}
      layout={layout}
      config={{ displayModeBar: false, responsive: true }}
      useResizeHandler
      style={{ width: '100%', height: '280px' }}
    />
  )
}
