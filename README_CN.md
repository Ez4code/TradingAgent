# A 股 Alpha Factory 研究系统中文说明

本文档面向受过高等教育、但没有专业计算机或专业金融背景的读者。目标是让你能够清楚理解这个项目在做什么、怎么运行、输出结果怎么看、哪里可能出错，以及后续如何安全地继续开发。

本项目只用于因子研究，不提供投资建议，不连接实盘交易，也不保证收益。

## 1. 项目在解决什么问题

本项目试图回答一个研究问题：在 A 股数据中，某些可以被明确规则描述的“因子”是否具有稳定的预测能力。

这里的“因子”可以理解为一种股票打分规则。例如：

- 最近 20 天涨得多的股票，未来是否还更容易上涨。
- 最近 20 天波动小的股票，未来是否表现更稳定。
- 成交量突然放大后，价格是否容易反转。

项目的核心思想是先做研究闭环，而不是一开始就做复杂交易平台。完整流程是：

```text
数据 -> 因子生成 -> 因子计算 -> 横截面标准化 -> RankIC 评估 -> TopK 回测 -> 报告输出
```

## 2. 重要边界

请牢记以下边界：

- 本项目不是荐股系统。
- 本项目不是实盘交易系统。
- 回测结果不是未来收益承诺。
- 任何自然语言需求都不会直接变成可执行 Python 代码。
- LLM 只能选择已有模板，不能自由发明并直接运行因子代码。
- 新模板只能写入 proposal 文件，默认不会加入正式模板库。

## 3. 项目目录结构

核心目录如下：

```text
alpha_factory/
  main.py                    主流程入口
  config.py                  全局配置
  data/
    data_loader.py           数据加载，统一字段，计算 returns 和 future_return
    sample_data_generator.py demo 数据生成
    akshare_downloader.py    AKShare 数据下载与缓存
    raw_stock_data/          AKShare 缓存目录
  universe/
    universe_filter.py       股票池过滤
  factors/
    template_library.py      固定因子模板库
    factor_generator.py      根据规划结果生成因子计划
    factor_engine.py         安全执行因子模板
    operators.py             安全算子
    factor_request.py        自然语言请求结构
    llm_planner.py           DeepSeek / 规则解析规划器
  processing/
    normalizer.py            横截面 winsorize 和 zscore
    neutralizer.py           size 中性化
    signal_smoother.py       信号平滑
  evaluation/
    factor_evaluator.py      RankIC 评估
    metrics.py               简单指标工具
  backtest/
    backtester.py            TopK 多头回测
  reports/
    report_writer.py         报告输出
  outputs/                   所有生成结果
  examples/
    sample_data.csv          demo 数据
```

根目录还有：

```text
main.py       方便从项目根目录直接运行
AGENTS.md    项目规则和阶段目标
README_CN.md 本文档
```

## 4. 如何运行 demo 模式

demo 模式不需要真实行情数据。它会使用合成数据，适合检查代码是否能跑通。

在项目根目录运行：

```bash
python main.py
```

如果 `alpha_factory/examples/sample_data.csv` 不存在，程序会自动生成：

- 50 只股票
- 200 个交易日
- 字段包括 `date, symbol, open, high, low, close, volume, amount`

默认请求是：

```text
生成一组动量、反转、波动率基础因子
```

运行成功后，控制台会输出类似：

```text
Request: 生成一组动量、反转、波动率基础因子
Data mode: demo
momentum_20 | RankIC mean=..., sharpe_top50=...
```

## 5. 如何使用自然语言生成因子

可以通过 `--request` 输入中文需求：

```bash
python main.py --request "我想测试短期放量后的反转因子"
python main.py --request "生成一些低波动高流动性的因子"
python main.py --request "测试价量背离因子"
```

程序会先尝试调用 DeepSeek。如果没有 API key 或网络不可用，会自动回退到本地规则解析。

DeepSeek API key 的环境变量名称是：

```bash
DEEPSEEK_API_KEY
```

代码会先读取当前环境变量。如果没有找到，会尝试从 `~/.zshrc` 中读取。

## 6. 如何运行 AKShare 模式

AKShare 模式用于尝试下载真实 A 股历史数据。需要先安装依赖：

```bash
pip install akshare
```

运行示例：

```bash
DATA_MODE=akshare START_DATE=20240101 END_DATE=20241231 python main.py
```

为了测试时少下载一些股票，可以限制数量：

```bash
DATA_MODE=akshare AKSHARE_SYMBOL_LIMIT=20 START_DATE=20240101 END_DATE=20240131 python main.py
```

缓存文件会保存到：

```text
alpha_factory/data/raw_stock_data/{symbol}.csv
```

如果某只股票下载失败，程序会跳过它，不会中断全局运行。失败信息写入：

```text
alpha_factory/outputs/failed_symbols.csv
```

## 7. 关键配置说明

配置文件在：

```text
alpha_factory/config.py
```

常用配置：

```text
DATA_MODE              demo 或 akshare
START_DATE             AKShare 起始日期，例如 20240101
END_DATE               AKShare 结束日期，例如 20241231
ADJUST                 复权方式，默认 qfq
REQUEST_SLEEP_SECONDS  下载间隔，避免请求过快
MAX_RETRIES            下载失败重试次数
MIN_AMOUNT_THRESHOLD   最低成交额阈值
USE_A_SHARE_FILTERS    是否启用 A 股股票池过滤
AKSHARE_SYMBOL_LIMIT   限制下载股票数量，0 表示不限制
```

这些配置大多可以通过环境变量覆盖。例如：

```bash
DATA_MODE=akshare AKSHARE_SYMBOL_LIMIT=100 python main.py
```

## 8. 数据字段含义

系统统一要求以下字段：

```text
date    日期
symbol  股票代码
open    开盘价
high    最高价
low     最低价
close   收盘价
volume  成交量
amount  成交额
```

加载数据后，系统会额外计算：

```text
returns       close / 昨日 close - 1
future_return open_{T+2} / open_{T+1} - 1
```

`future_return` 是回测和 RankIC 的未来收益标签。注意它不是用来生成信号的，而是用来评估 T 日信号之后的表现。

## 9. 严格交易时序

本项目非常重视避免未来函数。

每个交易日 T 的流程是：

```text
T 日收盘及以前的数据 -> 计算 factor_T
factor_T -> 生成 signal_T
T+1 开盘 -> 模拟买入
T+2 开盘 -> 模拟卖出或换仓
收益 = open_{T+2} / open_{T+1} - 1
```

禁止用 T+1 或 T+2 的信息计算 T 日信号。

## 10. 因子模板库

正式模板在：

```text
alpha_factory/factors/template_library.py
```

当前支持：

```text
momentum              close / delay(close, N) - 1
reversal              -1 * momentum
volatility            std(returns, N)
inverse_volatility    -1 * std(returns, N)
price_volume_corr     correlation(close, volume, N)
amount_momentum       mean(amount, N) / delay(mean(amount, N), N) - 1
liquidity             mean(amount, N)
breakout              close / max(close, N) - 1
distance_to_ma        close / mean(close, N) - 1
turnover_proxy        volume / mean(volume, N)
```

合法窗口：

```text
[5, 10, 20, 40, 60]
```

## 11. 为什么禁止 eval

`eval` 可以把字符串当代码执行。它很危险，因为 LLM 或用户输入的内容如果被直接执行，可能造成安全风险。

本项目不使用 `eval`。所有因子都由本地 Python 函数明确实现，例如：

- `delay_by_symbol`
- `rolling_mean_by_symbol`
- `rolling_std_by_symbol`
- `rolling_corr_by_symbol`

这保证了 LLM 只能“选择模板”，不能“自由写代码执行”。

## 12. 因子处理流程

每个因子计算完成后，会经过以下处理：

1. 横截面 winsorize：每个日期内压缩极端值。
2. 横截面 zscore：每个日期内标准化成均值约 0、标准差约 1。
3. size 中性化：用 `log(amount)` 作为 size proxy，回归后取残差。
4. 信号平滑：按股票做 3 日 rolling mean。

如果某天样本不足或 `amount` 无效，size 中性化会回退到原始因子，并写 warning。

## 13. RankIC 是什么

RankIC 用来衡量因子排序和未来收益排序的相关性。

直观理解：

- 某天因子分高的股票，如果未来收益也更高，则 RankIC 偏正。
- 某天因子分高的股票，如果未来收益更低，则 RankIC 偏负。
- 如果没有关系，则 RankIC 接近 0。

本项目计算的是横截面 RankIC。也就是每个交易日，在所有股票之间比较排序关系。

不要把单只股票自己的时间序列相关性当作 RankIC。

## 14. TopK 回测逻辑

每个因子会做 TopK 多头回测：

```text
Top50
Top100
Top200
```

每日逻辑：

1. 按当日信号从高到低排序。
2. 选择前 K 只股票。
3. 如果可用股票少于 K，则选择全部可用股票。
4. 等权持有。
5. 使用 `future_return` 计算收益。
6. 根据每日持仓权重变化计算 turnover。
7. 按 `round_trip_cost = 0.0025` 扣交易成本。

demo 数据只有 50 只股票，所以 Top100 和 Top200 通常会退化为“选择所有可用股票”。

## 15. A 股交易约束实现状态

精确实现或尽力实现：

- 停牌或不可交易：如果缺价格、缺成交额、成交量为 0，则过滤。
- 低成交额：按 `MIN_AMOUNT_THRESHOLD` 过滤。
- 成交额 bottom 20%：按月过滤成交额最低的 20%。
- ST：如果缓存中有 `is_st` 或名称中包含 ST，则过滤。
- 上市不足 120 天：使用缓存中第一条可用交易日期近似。

近似实现：

- 涨停不可买。
- 跌停不可卖。
- 一字板不可交易。

这些约束目前使用 OHLC 近似检测，因为缓存字段没有精确涨跌停价格。系统会在 `final_summary.md` 中写 warning，不会声称完整精确。

## 16. 输出文件说明

所有输出都在：

```text
alpha_factory/outputs/
```

常用文件：

```text
factor_plan.json            自然语言请求解析后的计划
generated_factors.json      实际生成并执行的因子列表
rejected_factors.csv        被拒绝或跳过的因子
new_template_proposals.json 新模板提案，不会自动加入正式库
factor_report.csv           因子评估和回测总表
factors_simple_log.csv      因子运行日志
equity_curve.csv            每日权益曲线
backtest_report.json        回测详细指标
failed_symbols.csv          AKShare 下载失败股票
universe_monthly.csv        每月股票池记录
final_summary.md            总结和 warning
```

## 17. 如何阅读 factor_report.csv

重点字段：

```text
factor                 因子名称
template_name          来源模板
window                 时间窗口
rank_ic_mean           平均 RankIC
rank_ic_std            RankIC 标准差
rank_icir              rank_ic_mean / rank_ic_std
rank_ic_hit_rate       RankIC 为正的日期比例
coverage               有效样本覆盖率
sharpe_top50           Top50 回测 Sharpe
max_drawdown_top50     Top50 最大回撤
turnover_top50         Top50 总换手
excess_return_top50    Top50 相对 benchmark 的超额收益
concentration_risk     是否有集中度风险标记
```

注意：demo 数据是合成数据，不要对它的收益指标做真实投资解释。

## 18. 常见问题排查

### 18.1 `ModuleNotFoundError: No module named 'pandas'`

说明 Python 环境缺少 pandas。安装：

```bash
pip install pandas numpy
```

### 18.2 AKShare 模式提示未安装

安装：

```bash
pip install akshare
```

### 18.3 AKShare 下载失败

先查看：

```text
alpha_factory/outputs/failed_symbols.csv
alpha_factory/outputs/final_summary.md
```

常见原因：

- 网络不可用。
- AKShare 未安装。
- AKShare 接口变更。
- 请求过快被限制。

可以尝试：

```bash
REQUEST_SLEEP_SECONDS=1 MAX_RETRIES=5 DATA_MODE=akshare python main.py
```

### 18.4 DeepSeek 没有调用成功

查看控制台：

```text
Planner mode: llm
```

表示调用成功。

如果看到：

```text
Planner mode: rule_based
```

说明回退到了本地规则解析。常见原因：

- `DEEPSEEK_API_KEY` 没有配置。
- 网络不可用。
- API 返回格式异常。

### 18.5 为什么 Top50 / Top100 / Top200 结果一样

demo 数据只有 50 只股票。如果股票数少于 K，系统会选择全部可用股票。所以 Top100 和 Top200 会退化为同一组股票。

真实 A 股数据足够多时，这三个组合才会明显不同。

## 19. 开发新因子的正确方式

推荐流程：

1. 先确认现有模板是否已经能表达需求。
2. 如果不能表达，写入 `new_template_proposals.json`，不要直接加入正式库。
3. 检查新模板是否有明确金融含义。
4. 检查是否只是已有模板改名、换窗口或正负号反转。
5. 使用已有安全算子实现。
6. 确认没有未来函数。
7. 运行 RankIC 和回测。
8. 检查与已有模板相关性是否过高。

正式加入模板库前，需要人工审核。

## 20. 修改代码时的建议顺序

如果你想继续开发，建议按以下顺序：

1. 先运行 `python main.py`，确认基线可跑。
2. 只改一个小模块。
3. 再运行 `python main.py`。
4. 检查 `factor_report.csv` 和 `final_summary.md`。
5. 如果涉及数据下载，检查 `failed_symbols.csv`。
6. 如果涉及回测，检查 `equity_curve.csv` 和 `backtest_report.json`。

不要一次性大改多个模块。这样更容易定位问题。

## 21. 最小验证命令

每次修改后，建议至少运行：

```bash
python -m compileall alpha_factory main.py
python main.py
```

如果测试自然语言请求：

```bash
python main.py --request "测试价量背离因子"
```

如果测试 AKShare 但不想下载太多：

```bash
DATA_MODE=akshare AKSHARE_SYMBOL_LIMIT=5 START_DATE=20240101 END_DATE=20240131 python main.py
```

也可以先单独预下载，再运行分析。这样更适合大量股票，因为下载和研究可以分开排查。

直接预下载指定股票：

```bash
python -m alpha_factory.data.akshare_downloader \
  --symbols sh600519,sz000001 \
  --download-dir alpha_factory/data/raw_stock_data \
  --start-date 20260126 \
  --end-date 20260424 \
  --adjust qfq \
  --workers 2 \
  --delay 0.5 \
  --max-retries 2
```

直接预下载股票列表中的前 300 只：

```bash
python -m alpha_factory.data.akshare_downloader \
  --list-csv /Users/liuxin/Project/AstockSelector/data/Astock_list.csv \
  --download-dir alpha_factory/data/raw_stock_data \
  --start-date 20260126 \
  --end-date 20260424 \
  --adjust qfq \
  --workers 4 \
  --limit 300 \
  --delay 0.5 \
  --max-retries 3
```

预下载完成后，运行同一批股票的分析：

```bash
DATA_MODE=akshare \
AKSHARE_SYMBOLS=sh600519,sz000001 \
START_DATE=20260126 \
END_DATE=20260424 \
USE_A_SHARE_FILTERS=0 \
python main.py --request "少妇战法，等J来"
```

如果使用列表前 300 只作为研究范围：

```bash
DATA_MODE=akshare \
ASTOCK_LIST_CSV=/Users/liuxin/Project/AstockSelector/data/Astock_list.csv \
AKSHARE_SYMBOL_LIMIT=300 \
AKSHARE_WORKERS=4 \
START_DATE=20260126 \
END_DATE=20260424 \
USE_A_SHARE_FILTERS=0 \
python main.py --request "少妇战法，等J来"
```

主流程会先检查缓存。如果所需股票在指定日期范围内已经缓存好，就直接开始分析；如果缺失或缓存日期不足，才会尝试下载。

## 22. 研究结果如何判断

不要只看单个指标。

较健康的因子通常需要同时观察：

- RankIC 均值是否稳定偏正或偏负。
- RankIC hit rate 是否明显高于 50%。
- RankICIR 是否较好。
- TopK 回测是否有稳定超额收益。
- 最大回撤是否可接受。
- 换手率是否过高。
- Top50 是否远好于 Top100 / Top200。

如果 Top50 很好，但 Top100 和 Top200 很差，可能只是少数股票驱动，系统会标记 `concentration_risk`。

## 23. 当前阶段没有做什么

当前阶段仍然没有做：

- 实盘交易。
- 自动下单。
- 精确涨跌停价格计算。
- 完整 A 股上市状态和停牌状态数据库。
- 完整财务数据因子。
- 分行业中性化。
- 组合优化。
- 参数自动寻优。

这些都应该在后续阶段谨慎加入。

## 24. 安全原则

继续开发时请保持以下原则：

- 不使用 `eval`。
- 不让 LLM 直接生成并执行 Python 代码。
- 所有因子来自模板库。
- 所有数据字段显式映射。
- 所有失败都要记录，不要假装成功。
- 所有近似实现都要写 warning。
- 始终保持 `python main.py` 可运行。

## 25. 一句话总结

这个项目是一个可复现的 A 股因子研究流水线。它用固定模板和安全算子生成因子，用严格交易时序避免未来函数，用 RankIC 和 TopK 回测检验信号，并把所有不确定或无法精确实现的地方写入 warning，方便后续继续开发。
