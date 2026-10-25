# 美股研究与邮件简报 Bot

本地 Python + SQLite + Flask + Docker Compose 项目。用于人工观察与筛股，没有券商下单接口、不维护推定持仓、不输出仓位或强制止损。研究优先级针对约1—3周的观察价值，长期估值不表示三周目标价。

**交付状态：可运行的研究工作台与模拟端到端版本，非已上线生产系统。** 行情/股票池、FRED、SEC原始文件及RSS有真实接口实现；本次无API密钥，未完成付费数据和真实SMTP联调。全面财务核验、事件定性、可比估值仍依赖带来源的人工或上游研究数据；缺失时降级/淘汰，不自动生成“低估”结论。

## 1. 最快开始（无需密钥）

建议 Python 3.12。Windows PowerShell：

```powershell
cd equity_bot
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
python -m equitybot run --demo --asof 2026-10-23
python -m equitybot serve
```

macOS / Linux：

```bash
cd equity_bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
cp .env.example .env
python -m equitybot run --demo --asof 2026-10-23
python -m equitybot serve
```

打开 http://127.0.0.1:8080 。页面包含精选、完整研究池、淘汰原因、历史快照、前向审计。`examples/` 提供可直接打开的演示HTML和邮件EML。模拟公司全部以 `DEMO` 开头，禁止实际发送模拟邮件。

`.env` 自动加载；已有系统环境变量优先。仅支持简单 `KEY=value`，不执行Shell、不展开变量。不要把密码发到聊天里，也不要提交 `.env`。

## 2. 常用命令

```bash
# 单次运行：默认读取 .env，默认 demo，自动选最近完整美股交易日
python -m equitybot run
# 重新导出最近报告的邮件预览（不发送）
python -m equitybot preview --output preview.html
# 定时常驻；NYSE交易日收盘后75分钟，使用真实日历与美东时区
python -m equitybot schedule
# 明确开启发送后，单次发信；仍有双开关保护
python -m equitybot run --send
# 定时发送同样必须显式传 --send
python -m equitybot schedule --send
# 反馈以公司ID为键，只影响软排序±2分，原因保留
python -m equitybot feedback fictional-0 favorite --reason "值得继续研究"
python -m equitybot feedback fictional-1 uninterested --reason "不了解商业模式"
# 前向研究审计（文件结构见DATA_CONTRACT）
python -m equitybot audit examples/forward_demo.json
python -m pytest -q
```

定时任务只有当日到期后才运行；周末不补发。机器休眠期间无法运行，恢复在同一交易日内会补跑；不会补造过去交易日的实时基本面。运行失败每60秒重试；邮件进入 `unknown` 状态不自动重发。没有实现常驻任务的高可用集群，请只运行一个 scheduler。

## 3. Docker Compose

```bash
cp .env.example .env
# Windows改用 Copy-Item
# 初次创建 .env 后执行：
docker compose build
docker compose run --rm scheduler python -m equitybot run --demo --asof 2026-10-23
docker compose up -d
```

访问 http://127.0.0.1:8080 。`ui`、`scheduler` 共用命名数据卷；端口只映射到本机。默认定时预览。若要定时发送，把 compose.yaml 的 scheduler command 改为 `["python", "-m", "equitybot", "schedule", "--send"]`，同时设置 `MAIL_SEND_ENABLED=true`。本次环境未安装Docker，镜像构建及Compose启动尚未实际测试。

真实模式证据文件可放在 `examples/evidence.json`，设置 `BOT_EVIDENCE=examples/evidence.json`；该目录已只读挂载。不要把真实密钥写进 examples。修改 config.json 后容器直接读取挂载文件。

## 4. 接入真实数据

先阅读 [数据接口与费用](docs/SOURCES.md) 和 [数据契约](docs/DATA_CONTRACT.md)。

1. 申请 Massive 行情权限，设置 `BOT_PROVIDER=massive`、`MASSIVE_API_KEY`。股票池由分页接口获取；只处理普通股和ADR及允许的交易所。`max_symbols=0` 不截断股票池。
2. 配置 `FRED_API_KEY` 获取VIX、信用利差、准备金、SOFR、IORB、逆回购、贴现窗口等。每项保存观察日期；不会把周度指标冒充当天值。
3. 配置 `SEC_USER_AGENT=姓名 邮箱`。自动保存对应公司 SEC companyfacts 原始版本；**原始XBRL不等于已标准化、核验完成的财务报表**。
4. 准备 `evidence.json`：公司是否SPAC、核验财务数据、ADR比例、必要的行业事件证据和估值假设。没有证据时不伪造，关键财务或身份未知会淘汰，因此仅填行情密钥可能得到0只。
5. `NEWS_RSS_URLS` 填合法公开、可信发布者的RSS地址，英文逗号分隔。获取原站公开摘要，不绕过付费墙。RSS标题不足以支持结论；公司名称匹配只标为未核验媒体报道。直接公告/独立核验新闻可通过证据文件加入。
6. 执行 `python -m equitybot run`，先查看淘汰原因与数据日期，再设置邮件。

真实适配器只接受最近已完成交易日。历史复现必须使用保存的时点输入快照，不能使用当前财务反推历史。免费行情套餐、限流和全市场扫描耗时可能无法满足收盘后75分钟的目标；应先用小范围 `max_symbols` 测试权限（报告明确说明覆盖截断），再购买合适权限、提高配置限速。不得因为套餐不支持而把旧行情标为当天。

另可使用 `BOT_PROVIDER=file`、`BOT_INPUT=examples/input_demo.json` 导入标准快照。这是替换商业数据商最直接的接口，输入的 `mode=demo` 将始终保留模拟标记。不要把示例改为live当真实数据用。

## 5. 确定性规则

- 公司总市值严格大于50亿美元；最近20个完整交易日日均成交额严格大于1000万美元；最近5个完整交易日高低差除以窗口前一交易日收盘价严格大于5%。
- 成交额优先读取 `turnover`，否则用原始 close×volume 并明确标为近似。不把VWAP×成交量暗称真实金额。
- 原始OHLC统一乘拆股因子，成交股数除因子；分红不混入高低价振幅。本版收益指标为价格收益、不含分红。
- 至少20个连续完整交易日；60日指标不足只显示缺失，不新增硬门槛。ADR使用交易凭证价格/成交股数与公司总市值；不拿普通股总股数乘ADR价格。
- 无PE上限，负盈利/极低盈利的PE不适用。金融/REIT专门估值未实现，显示暂不覆盖。
- 50→10；同公司去重；统一SIC细分行业最多2只，未知行业统一进同一个UNKNOWN组。无行业数据不能绕过限制。
- 观察候选也必须满足全部硬条件；企业关键财务无法核验或严重财务风险不能凑数。市场恐慌不会关闭选股。
- 综合分只是研究优先级：质量检查40、完整估值证据25、事件证据20、企稳10、核验新闻5；反馈±2。没有未校准上涨概率。
- 市场摘要与每只正文均≤100个非空白字符；这是采用你要求中更严格的上限。超限切换完整短句模板，不截断句子。

## 6. 数据与邮件可靠性

SQLite记录不可变运行快照、配置、输入与代码指纹、反馈、发送状态及审计；原始数据及报告保存在 `data/snapshots`，邮件在 `data/reports`，HTTP缓存在 `data/cache`。所有淘汰原因可查看。

同交易日/模式/收件人邮件键唯一，即便输入修订也不会重复发送。发送前失败可重试最多3次；SMTP已开始发送后断线可能已经被服务器接受，记 `unknown`，禁止自动重发。SMTP本身不支持严格exactly-once；需查看邮件服务器日志后人工处理数据库记录。程序不自动删除不确定记录。

推荐SMTP 587 STARTTLS。本版不支持仅465隐式TLS的SMTP服务；先确认你的邮箱支持587和应用密码。SMTP连接、密码从环境变量读取；日志不输出凭据。默认预览，即使配置SMTP也不会自动发出。

本地Web只读，无账户系统；反馈通过CLI。不应直接暴露到公网。Docker数据卷需要自行备份，可复制SQLite和snapshots目录；备份时先停止运行任务。

## 7. 大模型可选

设置 `LLM_BASE_URL`、`LLM_MODEL`、可选 `LLM_API_KEY`，支持本地或云端OpenAI兼容 `/chat/completions`。当前模型仅从代码构建的已约束摘要中选择表达，不自由生成财务数字、估值或证券名单。模型失败回退模板。所有硬筛、行业限制、数据时点、数值计算与字数检查仍由代码完成。

## 8. 边界与未完成的生产覆盖

- 当前研究质量高度依赖输入证据。没有实现自动阅读每家公司完整10-K/20-F并独立核验承诺、债务到期及竞争地位；这些检查缺项会显示unknown。
- 历史估值/可比公司选择、事件A/B/C定性需有来源的上游研究；系统校验并计算场景，不声称机器已经独立验证所有假设。资源企业可使用商品/产量/成本/资本开支场景，不按高资本开支直接排除。
- 支持稳定盈利、DCF增长、资源周期、分部估值计算；没有默认行业目标倍数或虚构预测。金融/REIT暂不覆盖；其他周期企业应提供自有中周期估值证据。
- 市场宽度只计算成功获取行情的初筛子样本，明确标记非全市场；尚无完整上涨/下跌成交量、52周新高低和VIX期限结构源。
- 单位目前规范为USD；非USD财务必须先按有来源的汇率标准化，不做静默币种猜测。ADR披露频率较低时可显式调整财务时效配置并记录原因。
- 股票及行业收益缺少可靠基准时显示缺失；现金分红未进入收益，审计不是总回报。
- 前向审计需要新的行情文件输入；已实现5/10/15交易日价格、相对收益、MFE/MAE计算与持久化，未声称有历史时点/退市数据库支持的回测绩效。
- 新闻摘要近似匹配去重不能保证识别所有跨语言转载，事件ID与人工核验可补强。

实际测试结果和联调边界见 [验收记录](docs/VALIDATION.md)。
