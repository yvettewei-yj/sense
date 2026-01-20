#!/usr/bin/env python3
"""
腾讯自选股 - 产品经理用户Sense训练系统
通过模拟小白用户对话，训练产品经理的用户理解能力
"""
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from config import USER_PROFILES, EVALUATION_CRITERIA
from user_simulator import UserSimulator, create_simulator
from evaluator import ConversationEvaluator, calculate_weighted_score

console = Console()


def print_welcome():
    """打印欢迎信息"""
    welcome_text = """
# 🎯 腾讯自选股 - PM用户Sense训练系统

欢迎来到产品经理用户感知训练平台！

在这里，你将扮演腾讯自选股的产品经理/客服，
与各种背景的「小白用户」进行对话，
目标是理解他们的需求、解答他们的疑虑，
最终说服他们开户使用我们的产品。

## 训练目标
- 🎯 提升用户同理心
- 💬 学会用通俗语言解释专业概念  
- 🔍 识别用户真实需求和顾虑
- 🤝 建立信任并引导转化
"""
    console.print(Panel(Markdown(welcome_text), border_style="cyan", box=box.DOUBLE))


def show_user_profiles():
    """显示可选的用户画像"""
    table = Table(title="📋 可选用户画像", box=box.ROUNDED, border_style="blue")
    table.add_column("ID", style="cyan", justify="center", width=4)
    table.add_column("姓名", style="green", width=8)
    table.add_column("年龄", justify="center", width=6)
    table.add_column("职业", style="yellow", width=12)
    table.add_column("触发场景", style="white", width=35)
    table.add_column("难度", justify="center", width=8)
    
    difficulty_map = {
        (1, 5): "⭐ 简单",
        (6, 7): "⭐⭐ 中等",
        (8, 10): "⭐⭐⭐ 困难"
    }
    
    for profile in USER_PROFILES:
        threshold = profile["trust_threshold"]
        difficulty = "⭐ 简单"
        for (low, high), label in difficulty_map.items():
            if low <= threshold <= high:
                difficulty = label
                break
                
        table.add_row(
            str(profile["id"]),
            profile["name"],
            str(profile["age"]),
            profile["occupation"],
            profile["trigger_scenario"][:35] + "..." if len(profile["trigger_scenario"]) > 35 else profile["trigger_scenario"],
            difficulty
        )
    
    console.print(table)
    console.print()


def show_user_detail(profile: dict):
    """显示用户详细信息"""
    detail_text = f"""
**👤 {profile['name']}** ({profile['age']}岁 · {profile['occupation']})

**📖 背景故事**
{profile['background']}

**🎯 投资目标**
{profile['investment_goal']}

**⚠️ 风险承受能力**: {profile['risk_tolerance']}

**😰 主要顾虑**
{chr(10).join(['• ' + p for p in profile['pain_points']])}

**🎬 触发场景**
{profile['trigger_scenario']}

**🎭 性格特点**
{profile['personality']}

**📊 说服难度**: 信任度需达到 {profile['trust_threshold']}/10 才会考虑开户
"""
    console.print(Panel(Markdown(detail_text), title="用户档案", border_style="green", box=box.ROUNDED))


def show_status_bar(simulator: UserSimulator, turn_count: int):
    """显示状态栏"""
    trust = simulator.trust_level
    threshold = simulator.profile["trust_threshold"]
    
    # 信任度进度条
    filled = "█" * trust
    empty = "░" * (10 - trust)
    trust_bar = f"[{'green' if trust >= threshold else 'yellow'}]{filled}[/][dim]{empty}[/]"
    
    # 已解答顾虑
    total_concerns = len(simulator.profile["pain_points"])
    addressed = len(simulator.concerns_addressed)
    
    status = f"""
╭─────────────────────────────────────────────────────────────────╮
│  🎯 对话轮数: {turn_count:2d}  │  💚 信任度: {trust_bar} {trust}/{threshold}  │  ✅ 已解答: {addressed}/{total_concerns}  │
╰─────────────────────────────────────────────────────────────────╯"""
    
    console.print(status)


def run_training_session(profile_id: int):
    """运行一次训练会话"""
    # 创建用户模拟器
    simulator = create_simulator(profile_id)
    evaluator = ConversationEvaluator()
    
    console.print()
    show_user_detail(simulator.profile)
    console.print()
    
    console.print(Panel(
        "[bold yellow]训练即将开始！[/]\n\n"
        "你是腾讯自选股的产品经理/客服，需要与这位用户对话。\n"
        "目标：理解需求 → 解答疑虑 → 建立信任 → 引导开户\n\n"
        "[dim]输入 /quit 可随时结束对话[/]",
        border_style="yellow",
        box=box.ROUNDED
    ))
    
    console.print()
    input("按 Enter 键开始对话...")
    console.print()
    
    # 生成用户开场白
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]用户正在思考..."),
        transient=True,
        console=console
    ) as progress:
        progress.add_task("thinking", total=None)
        opening = simulator.get_opening_message()
    
    turn_count = 0
    
    # 显示用户开场白
    console.print(Panel(
        f"[bold]{simulator.profile['name']}[/]: {opening['response']}",
        border_style="blue",
        box=box.ROUNDED,
        title="👤 用户"
    ))
    
    # 主对话循环
    while True:
        turn_count += 1
        show_status_bar(simulator, turn_count)
        
        # 获取PM输入
        console.print()
        pm_input = Prompt.ask("[bold green]你的回复[/]")
        
        if pm_input.lower() in ['/quit', '/exit', '/q']:
            console.print("[yellow]对话已结束[/]")
            break
            
        if not pm_input.strip():
            console.print("[red]请输入有效内容[/]")
            turn_count -= 1
            continue
        
        # 获取用户回复
        console.print()
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]{simulator.profile['name']}正在思考..."),
            transient=True,
            console=console
        ) as progress:
            progress.add_task("thinking", total=None)
            response = simulator.respond(pm_input)
        
        # 显示用户回复
        console.print(Panel(
            f"[bold]{simulator.profile['name']}[/]: {response['response']}",
            border_style="blue",
            box=box.ROUNDED,
            title="👤 用户"
        ))
        
        # 显示隐藏信息（调试用，实际可注释掉）
        if response.get("inner_thought"):
            console.print(f"  [dim italic]💭 (用户内心: {response['inner_thought']})[/]")
        if response.get("trust_change", 0) != 0:
            change = response["trust_change"]
            symbol = "📈" if change > 0 else "📉"
            console.print(f"  [dim]{symbol} 信任度变化: {'+' if change > 0 else ''}{change}[/]")
        
        # 检查是否成功
        if simulator.is_convinced:
            console.print()
            console.print(Panel(
                f"🎉 [bold green]恭喜！{simulator.profile['name']}已被你说服，准备开户！[/]",
                border_style="green",
                box=box.DOUBLE
            ))
            break
            
        # 检查是否放弃
        if not response.get("willing_to_continue", True):
            console.print()
            console.print(Panel(
                f"😔 [bold red]{simulator.profile['name']}对对话失去了兴趣...[/]",
                border_style="red"
            ))
            break
            
        # 限制轮数
        if turn_count >= 20:
            console.print()
            console.print(Panel(
                "⏰ [yellow]对话轮数已达上限（20轮）[/]",
                border_style="yellow"
            ))
            break
    
    # 进行评估
    console.print()
    console.print("[bold cyan]正在生成评估报告...[/]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]AI正在分析对话..."),
        transient=True,
        console=console
    ) as progress:
        progress.add_task("evaluating", total=None)
        evaluation = evaluator.evaluate(
            simulator.conversation_history,
            simulator.profile,
            simulator.trust_level,
            simulator.is_convinced,
            simulator.concerns_addressed,
            turn_count
        )
    
    # 显示评估结果
    show_evaluation_report(evaluation, simulator, turn_count)
    
    return evaluation


def show_evaluation_report(evaluation: dict, simulator: UserSimulator, turn_count: int):
    """显示评估报告"""
    console.print()
    
    # 总分
    total = evaluation.get("total_score", 0)
    grade = "S" if total >= 90 else "A" if total >= 80 else "B" if total >= 70 else "C" if total >= 60 else "D"
    grade_color = "green" if grade in ["S", "A"] else "yellow" if grade in ["B", "C"] else "red"
    
    console.print(Panel(
        f"[bold {grade_color}]综合评分: {total:.1f}/100 (等级: {grade})[/]",
        title="📊 评估报告",
        border_style=grade_color,
        box=box.DOUBLE
    ))
    
    # 维度分数
    scores = evaluation.get("scores", {})
    score_table = Table(title="各维度得分", box=box.ROUNDED, border_style="cyan")
    score_table.add_column("维度", style="cyan", width=15)
    score_table.add_column("得分", justify="center", width=10)
    score_table.add_column("评价", width=40)
    
    for key, criteria in EVALUATION_CRITERIA.items():
        score = scores.get(key, 0)
        level = "优秀" if score >= 80 else "良好" if score >= 60 else "需提升"
        color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
        score_table.add_row(
            criteria["name"],
            f"[{color}]{score}[/]",
            f"[dim]{criteria['description']}[/]"
        )
    
    console.print(score_table)
    
    # 对话统计
    stats_text = f"""
**📈 对话统计**
- 对话轮数: {turn_count}轮
- 最终信任度: {simulator.trust_level}/10
- 结果: {'✅ 成功说服' if simulator.is_convinced else '❌ 未能说服'}
- 解答顾虑: {len(simulator.concerns_addressed)}/{len(simulator.profile['pain_points'])}
"""
    console.print(Panel(Markdown(stats_text), border_style="blue", box=box.ROUNDED))
    
    # 亮点
    highlights = evaluation.get("highlights", [])
    if highlights:
        highlight_text = "\n".join([f"✅ {h}" for h in highlights])
        console.print(Panel(highlight_text, title="💪 做得好的地方", border_style="green", box=box.ROUNDED))
    
    # 改进建议
    improvements = evaluation.get("improvements", [])
    if improvements:
        improvement_text = "\n".join([f"📌 {i}" for i in improvements])
        console.print(Panel(improvement_text, title="🎯 改进建议", border_style="yellow", box=box.ROUNDED))
    
    # 关键洞察
    insights = evaluation.get("key_insights", "")
    if insights:
        console.print(Panel(
            f"[italic]{insights}[/]",
            title="💡 用户Sense关键洞察",
            border_style="magenta",
            box=box.ROUNDED
        ))
    
    # 总体评价
    comment = evaluation.get("overall_comment", "")
    if comment:
        console.print(Panel(comment, title="📝 总体评价", border_style="cyan", box=box.ROUNDED))


def main():
    """主函数"""
    print_welcome()
    
    while True:
        console.print()
        show_user_profiles()
        
        # 选择用户
        try:
            choice = IntPrompt.ask(
                "请选择要训练的用户ID (输入0退出)",
                choices=[str(i) for i in range(len(USER_PROFILES) + 1)]
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]再见！[/]")
            break
            
        if choice == 0:
            console.print("[cyan]感谢使用，再见！👋[/]")
            break
            
        if choice < 1 or choice > len(USER_PROFILES):
            console.print("[red]无效的选择，请重试[/]")
            continue
        
        # 运行训练
        try:
            run_training_session(choice)
        except KeyboardInterrupt:
            console.print("\n[yellow]训练已中断[/]")
        except Exception as e:
            console.print(f"[red]发生错误: {e}[/]")
            import traceback
            traceback.print_exc()
        
        # 询问是否继续
        console.print()
        if not Confirm.ask("是否继续训练?", default=True):
            console.print("[cyan]感谢使用，再见！👋[/]")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]程序已退出[/]")
        sys.exit(0)
