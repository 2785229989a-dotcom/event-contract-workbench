# 事件合约预测工作台 (Event Contract Prediction Workbench)

基于 Polymarket 公开 API 的综合预测市场分析与模拟交易工具。

## 功能

| 模块 | 说明 |
|------|------|
| 市场总览 | 实时高成交量事件列表、概率分布、成交量排行 |
| 市场详情与监控 | 订单簿、价格历史图表、监控列表 |
| 模拟交易 | 虚拟资金纸上交易，记录持仓与交易历史 |
| 策略回测 | 均值回归 / 动量突破简单回测，权益曲线 |
| 数据分析 | 概率-成交量散点、极端市场筛选、统计 |

## 快速启动

pip install -r requirements.txt
streamlit run app.py
