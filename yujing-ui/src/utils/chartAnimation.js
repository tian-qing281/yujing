// ECharts 入场动画预设
// 统一缓动：cubicOut；按图表类型分配时长
// 用法：setOption({ ...ANIM.bar, ...option })

export const ANIM = {
  // 柱状图：左→右 / 下→上 错峰 80ms
  bar: {
    animation: true,
    animationDuration: 700,
    animationEasing: "cubicOut",
    animationDelay: (idx) => idx * 80,
    animationDurationUpdate: 300,
    animationEasingUpdate: "cubicOut",
  },
  // 饼图：旋转 + 缩放
  pie: {
    animation: true,
    animationDuration: 700,
    animationEasing: "cubicOut",
    animationDurationUpdate: 300,
  },
  // 雷达图：从中心展开
  radar: {
    animation: true,
    animationDuration: 800,
    animationEasing: "cubicOut",
    animationDurationUpdate: 300,
  },
  // 折线/面积图：左→右 unroll
  line: {
    animation: true,
    animationDuration: 700,
    animationEasing: "cubicOut",
    animationDelay: (idx) => idx * 30,
    animationDurationUpdate: 300,
  },
};
