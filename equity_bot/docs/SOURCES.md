# 官方接口核验记录

查阅日期：2026-10-25。价格和套餐会变化，以订阅时官方页面及账户权限为准。本次仅查阅官方文档，未使用API密钥验证账户权限。

| 来源 | 接口/用途 | 权限、覆盖与注意事项 |
|---|---|---|
| [Massive All Tickers](https://massive.com/docs/rest/stocks/tickers/all-tickers) | `/v3/reference/tickers` 分页股票池 | 市场含多证券类型，代码明确筛选CS/ADRC和交易所；并非指数成分股替代全市场 |
| [Ticker Overview](https://massive.com/docs/rest/stocks/tickers/ticker-overview) | `/v3/reference/tickers/{ticker}` 公司市值、CIK、SIC | 公司市值采用供应商公司级口径；不重新乘股数；身份/ADR比例需要证据 |
| [Custom Bars](https://massive.com/docs/rest/stocks/aggregates/custom-bars) | `/v2/aggs/ticker/{symbol}/range/1/day/{from}/{to}` | 同时请求raw与split-adjusted，逐日对照价格比例；默认不是分红总回报；日Bar按来源合格成交口径，不能宣称纯常规交易时段 |
| [Massive Pricing](https://massive.com/pricing) | 行情套餐 | 查阅时Basic免费5次/分；Starter 29美元/月、15分钟延迟；Developer 79美元/月。不是保证全部财务/新闻端点免费，也未作购买推荐 |
| [Massive FAQ](https://massive.com/knowledge-base/categories/faq) | 日行情可用时间 | 免费Basic当日REST bars可能须午夜后才可取，不能保证收盘+75分钟；平日全市场逐证券请求也受调用成本限制 |
| [SEC API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` | 无API密钥；需识别User-Agent。自定义XBRL标签、不同财年/YTD/重述/IFRS无法通用猜测 |
| [SEC Developer](https://www.sec.gov/about/developer-resources) | 访问规则 | 官方总请求上限10次/秒；代码默认远低于该值，用户提高http_rpm也建议不超过300 |
| [FRED observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) | `/fred/series/observations` | 需要FRED key；传入实时期与观察截止日，保留观察日期，不伪装成实时市场行情 |
| [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars) | XNYS日历 | 本地处理交易日、夏令时、提前收盘；包版本记录在requirements-tested.txt |

FRED使用 VIXCLS、BAMLH0A0HYM2、WRESBAL、SOFR、IORB、RRPONTSYD、WLCFLPCL。各项单位在代码中独立定义，SOFR-IORB仅相同观察日期才计算。SOFR-IORB是隔夜融资相对准备金利率的参考差值，不是降息信号。日度5自然日、周度14自然日以上标记陈旧，缺失不补零。

RSS由用户配置新闻网站官方公开地址，只读取原始公开摘要。不会调用付费墙绕过、模型记忆填数或执行网页指令；自动名称匹配也不代表独立事实核验。
