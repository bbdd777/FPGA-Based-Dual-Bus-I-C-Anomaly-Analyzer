# 可复用技能包

本目录包含两个Skill：

| Skill | 入口 | 用途 |
|---|---|---|
| FPGA总线分析仪学习指导 | [fpga-bus-analyzer-tutor](fpga-bus-analyzer-tutor/SKILL.md) | 结合课本和阶段小任务讲解采样、缓存、I2C、触发与传输；提供通俗中文、图解、Verilog代码风格和调试方法 |
| 工程证据与验证工作流 | [fpga-evidence-workflow](fpga-evidence-workflow/SKILL.md) | 从真实失败与纠错提炼参数绑定核验、源事件时间接口、黄金参考比对、证据分层和提示工作流 |

## FPGA指导Skill

`fpga-bus-analyzer-tutor/`于2026年10月26日从本项目实际使用的个人Skill目录原样收录，共8个文件：`SKILL.md`、`agents/openai.yaml`及6份`references/`参考。包含阶段任务、教材索引、项目约定、课本代码风格、讲解示例和阶段七接口边界，内部相对引用均随包保留。

调用名称为`$fpga-bus-analyzer-tutor`。使用时提供实际工程位置、当前问题及已验证进度。原版中的`F:/fpga嵌赛`、`G:/FPGA_test`和教材路径是本项目本机路径；其他使用者需按自己的资料位置对应查找。教材PDF、原始学习计划和历史工程没有随本Skill重复打包，历史绝对路径只用于来源定位。

其中V1的10MSa/s、32768点及阶段七接口属于教学路线和历史基线，不代表最终工程参数；最终四路50MSa/s、262144点及双路规则以[设计报告](../report/design_report.md)、[实现说明](../docs/design.md)和[验证证据](../report/evidence_index.md)为准。原版已经要求根据用户当前范围及验证证据判断进度；本次没有改写原Skill或把历史目标补成最终验收结论。

## 工程证据与验证Skill

`fpga-evidence-workflow/`适用于FPGA、MCU和电脑协作的采样、触发、传输及验证工程。使用方法：提供实际源码、日志、器件和参数，按SKILL.md及references执行，保留失败记录。

已验证效果：正式/诊断参数错配、MCU编译优化掉等待、源时间误用等问题已在本项目相应历史验证中定位；最终100轮另有独立实测归档。更换板卡、工具、接口或时钟域后必须重测；没有原始证据时只能提出假设，尚未进行陌生队伍跨项目量化复用实验。

参考真实协作过程：[AI精选](../report/ai_collaboration.md)及[176条可见对话正文](../report/ai_conversations.md)。本项目不使用PYNQ，不主张PYNQ专用加分。
