# 输入与证据数据契约

完整可运行标准样例：`examples/input_demo.json`。所有内容是合成数据，文件可直接供FileProvider复现。

## 根对象

- `mode`: demo/live。必须真实标记，demo永不发送邮件。
- `asof`: 最近完整交易日YYYY-MM-DD。
- `cutoff`: 带时区ISO时间；所有披露/抓取必须不晚于它。
- `stocks`: 证券数组；`market`: 摘要/指标/完整分析；`benchmark`: 可选市场基准OHLCV。
- `warnings`: 来源失败或覆盖限制列表。

## 证券及行情

`symbol,name,company_id,type,exchange,currency,market_cap,market_cap_currency,market_cap_scope,cap_asof,cap_source,price_source,is_spac`。

`company_id`必须是公司级稳定标识（优先CIK），跨股类/ADR共用同一标识。`type`只接受CS/ADRC；`is_spac`必须明确false。USD公司市值、USD证券价格。ADR还需 `adr_evidence.ordinary_shares_per_adr` >0，且附核验来源；不要将存托凭证单位和普通股单位混用。

`industry`包含 `taxonomy="SIC"`、四位细分行业code、name、source；分类缺失统一UNKNOWN。`sector`与`exposures`用于展示跨行业共同风险，不替代行业上限。

`bars`按日包含 `date,open,high,low,close,volume,split_factor`；可选 `turnover` 为数据源真实成交金额。OHLC与volume必须是同一原始交易证券的未调整数据。`split_factor`是将该日原始价格变为当前统一拆股单位的累积因子（无拆股为1）；raw价格×factor，raw volume÷factor。已经统一拆股调整过的输入可factor=1，但必须保持成交股数与价格同基准。分红不能混进split_factor。

20日平均金额只用最近20个完整且连续的交易日，行情数据缺一日不以19日替代。60日参考指标不足返回null；不因此额外硬淘汰。`rv20/rv60`为日对数收益样本标准差×√252，年化口径；5日振幅完全独立。ATR%为最近14个TrueRange的简单均值/最新收盘价，不是Wilder递推版。

## 通用来源对象

```json
{
  "source": "公司公告/SEC/供应商名称",
  "url": "https://来源/原文",
  "published_at": "2026-10-20T12:00:00+00:00",
  "fetched_at": "2026-10-23T21:15:00+00:00",
  "verified": true
}
```

`verified=true`是受信本地研究流程的声明，不意味着本程序已自动审阅原文。**只能由可靠数据适配器或完成核验的研究人员填写，不能让网页/LLM自行写true。** 程序检查来源字段、时点及有效值；不能凭URL本身证明内容真实。真实财务来源应指向对应申报文档，并保存本地版本或引用证据。供应商接口的asof是观察日期，不应误读为财报披露时间。

## financials

带来源对象，加 `period_end,version,currency,revenue,net_income,operating_cash_flow,capex,cash,debt,severe_risk`，可选 `ebit`。流量数字应使用同口径TTM或年度完整财报；不得混用单季度收入、YTD现金流和年度利润。必须记录 `period_type=TTM/FY`，可额外记录`period_start`、`accession`、`normalization_notes` 说明来源和口径。`capex`是正数现金支出；cash/debt为期末存量。缺失不能补0，确认为0须有来源。

`severe_risk`必须由核验流程明确false才可进入研究池。债务违约、持续经营重大不确定等应标true。不是凭市值大就默认false。

`checks`逐项来源、`status`（pass/risk/unknown）、`note`：
`revenue,earnings,cash_flow,receivables,inventory,one_offs,dilution,sbc,debt,interest,maturities,capex,leases,commitments,financing,competition,trend`。

本版不自动把高capex判差；应说明现金流覆盖、投资回报、融资能力。期末日期超过配置200天会淘汰，年度ADR可按披露制度显式配置合理时效，不静默放宽。

## valuation_evidence 与估值模型

- `historical`、`peers`：来源对象 + values数组 + comparability_explanation。说明增长、业务结构、利率及商业模式风险可比性。
- `scenarios`：来源对象 + assumptions + 公司权益价值bear/base/bull（USD，不是每ADR价格）。也可提供 `parameters` 的bear/base/bull对象，由代码计算。
- `business_model`: stable/growth/cyclical/conglomerate/financial/reit/unknown。

参数模型定义见 `equitybot/scenarios.py`：

| 模型 | 每个情景的参数 |
|---|---|
| stable | normalized_net_income, justified_pe；倍数来自证据，不要求用户输入“理想PE”，无默认统一倍数 |
| growth | fcff列表, discount_rate, terminal_growth, cash, debt, other_claims；明确终值敏感性 |
| cyclical（资源） | commodity_price, production, royalty_rate, unit_cash_cost, fixed_costs, tax_rate, maintenance_capex, growth_capex, working_capital_increase, discount_rate, terminal_growth, cash, debt, other_claims |
| conglomerate | segments数组（每项enterprise_value与分部证据）, cash, debt, holding_cost_value, other_claims |

资源模型为简化恒定现金流情景，须在假设中解释价格、产量、币种和国家风险折现率，不能自动当作储量消耗模型。其他周期企业提供核验过的中周期权益价值，不能硬套资源模型。

可选forecast：来源 + revenue_next, discount_rate, terminal_growth。仅在可靠预测存在时给出简化永续模型隐含FCF利润率；无预测返回null。

## event

来源对象 + date + classification(A/B/C/D) + counterevidence + channels。

channels要求 `revenue_orders,supply_production,commodity_transport,tariffs_sanctions,fx_funding` 每项带来源与影响说明。B类还须 estimated_loss_fraction（0—1）与loss_assumptions。缺通道、未来或陈旧证据降为D。

分类由提供证据的研究者/上游分析提出；本程序检查证据完整性，不声称能够仅靠新闻标题判断真实损伤。事件前OLS参数只用事件日前样本，超额回撤仅作线索。

## news

每条含来源对象、title、summary、entities、is_reprint（true/false/null未知）、kind（fact/media_report/inference）、可选event_id。同URL、同event_id、摘要高度相似去重；旧信息标background，转载URL保留但不算独立核验证据。无摘要不采信。抓取失败用news_status=failed/unavailable/partial，不等于无负面信息。

## Massive 证据覆盖文件

`evidence.json` 根对象以ticker为键，只能覆盖以下研究字段，不允许覆盖行情/市值/类型：
`is_spac,financials,business_model,exposures,valuation_evidence,event,adr_evidence,industry_bars,news,news_aliases`。

`examples/evidence.template.json` 提供空模板，故意保持未核验以防误用。`news_aliases`仅供公司实体匹配，不能用很短的ticker缩写混淆普通英文词。

## 前向审计输入

```json
{"mode":"demo", "prices":{"DEMO000":["这里应是完整OHLCV对象"]}, "benchmark":["完整OHLCV对象"]}
```

见可执行的 `examples/forward_demo.json`。必须同时包含入选日与之后完整交易日数据，并统一到最新拆股基准，避免之后拆股造成收益失真。5/10/15天未到期或缺日标记缺失；不会将第4天假装第5天。只更新audit表，不更新历史筛选快照。不含现金分红，非策略净值或实际交易收益。
