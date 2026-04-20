/**
 * ECharts 按需导入 · 全局唯一注册点
 *
 * 所有组件统一 `import { init, graphic } from "@/utils/echarts"` 取代 `window.echarts`。
 * 只注册项目实际用到的图表类型和组件，tree-shaking 后体积约为完整包的 30-40%。
 */
import { init, use, graphic } from "echarts/core";
import { BarChart, LineChart, PieChart, RadarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  RadarComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([
  BarChart,
  LineChart,
  PieChart,
  RadarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  RadarComponent,
  CanvasRenderer,
]);

// 向后兼容：部分组件仍通过 window.echarts 访问
window.echarts = { init, graphic };

export { init, graphic };
