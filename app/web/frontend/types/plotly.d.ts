// plotly.js-dist-min 은 자체 타입 선언을 제공하지 않는다.
// @types/plotly.js 는 dist-min 빌드와 형태가 달라 맞지 않으므로
// alpinejs.d.ts 와 같은 최소 ambient 선언으로 처리한다.
declare module "plotly.js-dist-min";
