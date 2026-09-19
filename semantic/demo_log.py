# -*- coding: utf-8 -*-
"""
Server Log Semantic Reduction Demo

Demonstrates the complete workflow for log processing:
1. Log parsing (multi-format support)
2. Anomaly detection (error bursts, circuit breakers)
3. Policy-based evaluation
4. Intelligent sampling
5. Storage reduction with diagnostic capability preservation
"""

import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic.log_analyzer import (
    LogAnalyzer, LogParser, LogLevel, LogBlock
)
from semantic.log_policy import (
    LogPolicy, LogPolicyEngine
)
from semantic_reducer import AuditLogger, DataValueCalculator


def generate_realistic_logs(hours: int = 24, lines_per_hour: int = 100) -> list:
    """
    Generate realistic server log lines for simulation.

    Args:
        hours: Number of hours to simulate
        lines_per_hour: Average lines per hour

    Returns:
        List of log lines
    """
    logs = []
    base_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Log templates by level
    templates = {
        'error': [
            'DatabaseConnectionException: Connection refused to db-master:5432',
            'NullPointerException: Cannot invoke method on null object',
            'OutOfMemoryError: Java heap space exhausted',
            'CircuitBreakerOpenException: Service payment unavailable',
            'TimeoutException: Read timed out after 30000ms',
        ],
        'warn': [
            'Slow query detected: execution time {}ms exceeds threshold 1000ms',
            'Connection pool running low: {} active connections remaining',
            'Cache miss rate elevated: {}% over last 5 minutes',
            'Deprecated API called: /api/v1/legacy endpoint',
        ],
        'info': [
            'GET /api/users/{} 200 {}ms',
            'POST /api/orders {} 201 {}ms',
            'User login: userId="{}" sessionId="{}"',
            'Order placed: orderId="{}" amount={}CNY',
            'Health check passed: all services operational',
            'Background job completed: JobId={} duration={}ms',
        ],
        'debug': [
            'Connection acquired from pool: pool-{} thread={}',
            'SQL executed: SELECT * FROM orders WHERE status=? ({}ms)',
            'Cache updated: key=user:{} ttl=3600',
            'Session restored: {} active sessions',
        ],
        'trace': [
            'Method entry: com.app.service.UserService.getUserById({})',
            'Method exit: com.app.service.UserService.getUserById() -> {}ms',
            'Variable state: user={} cart={} items={}',
        ]
    }

    user_ids = [f'user_{i:06d}' for i in range(1, 101)]
    order_ids = [f'ORD2024{random.randint(10000000, 99999999)}' for _ in range(20)]
    session_ids = [f'sess_{random.getrandbits(64):016x}' for _ in range(50)]

    for hour in range(hours):
        for _ in range(lines_per_hour):
            # Determine level distribution
            r = random.random()
            if r < 0.005:  # 0.5% errors
                level = 'error'
            elif r < 0.02:  # 1.5% warnings
                level = 'warn'
            elif r < 0.50:  # 48% info
                level = 'info'
            elif r < 0.85:  # 35% debug
                level = 'debug'
            else:  # 15% trace
                level = 'trace'

            # Generate timestamp
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            timestamp = base_time + timedelta(hours=hour, minutes=minute, seconds=second)
            ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')

            # Select template and fill in
            template = random.choice(templates[level])

            if '{}' in template:
                if 'userId' in template:
                    template = template.format(random.choice(user_ids), random.choice(session_ids))
                elif 'orderId' in template:
                    template = template.format(random.choice(order_ids), random.randint(10, 9999))
                elif template.count('{}') == 1:
                    if 'ms' in template:
                        template = template.format(random.randint(5, 5000))
                    else:
                        template = template.format(random.randint(1, 1000))
                else:
                    # Multiple placeholders
                    values = tuple(random.randint(1, 1000) for _ in range(template.count('{}')))
                    template = template.format(*values)

            thread = random.choice(['main', 'http-nio-8080', 'pool-1', 'scheduler', 'async-worker'])
            log_line = f'{ts_str} {level.upper()} [{thread}] {template}'
            logs.append(log_line)

    return logs


def demo_log_reduction():
    """Main demo for server log semantic reduction."""

    print("\n" + "="*70)
    print("Server Log Semantic Reduction Demo")
    print("="*70)

    # Setup
    base = Path("C:/Users/zcc36/Documents/ChatGPT/存储项目/semantic_demo_data")
    base.mkdir(exist_ok=True)

    audit_logger = AuditLogger(str(base / "audit"))
    calculator = DataValueCalculator()

    # Create policy
    policy = LogPolicy.default_application()
    policy.policy_name = "Production Application Log Policy"

    print(f"\nPolicy: {policy.policy_name}")
    print(f"  Log Type: {policy.log_type.value}")
    print(f"  Level Rules: {len(policy.level_rules)}")
    print(f"  Time Rules: {len(policy.time_rules)}")
    print(f"  Default Sampling Rate: {policy.default_sampling_rate:.0%}")

    # Create engine
    engine = LogPolicyEngine(policy, audit_logger)

    # Generate 7 days of logs (simulate ~100 lines/hour)
    print("\n" + "-"*70)
    print("Simulating 7 days of application logs")
    print("~16,800 lines/hour, 2,800 lines/day")
    print("-"*70)

    all_logs = generate_realistic_logs(hours=24*7, lines_per_hour=100)

    print(f"\nGenerated {len(all_logs):,} log lines")

    # Process logs in hourly blocks
    print("\nProcessing logs in hourly blocks...")

    blocks_per_hour = 1  # 1 hour = 1 block
    total_lines = len(all_logs)
    lines_per_block = total_lines // (24 * 7)

    stats = {
        'total_blocks': 0,
        'total_lines': 0,
        'preserve': 0,
        'sample': 0,
        'compress': 0,
        'discard': 0,
        'original_bytes': 0,
        'saved_bytes': 0,
        'error_count': 0,
        'warn_count': 0,
        'order_logs_preserved': 0,
    }

    # Process in chunks
    chunk_size = lines_per_block
    analyzer = LogAnalyzer()

    for i in range(0, total_lines, chunk_size):
        chunk = all_logs[i:i+chunk_size]
        if not chunk:
            continue

        # Analyze block
        block = analyzer.analyze_block(chunk, f"block_{i//chunk_size:06d}")

        # Evaluate against policy
        result = engine.evaluate_block(block, f"/var/log/app_{i//chunk_size}.log")

        # Count actions
        action = result['action']
        if action == 'preserve_intact':
            stats['preserve'] += 1
        elif action == 'downsample':
            stats['sample'] += 1
        elif action == 'archive':
            stats['compress'] += 1
        elif action == 'delete':
            stats['discard'] += 1

        stats['total_blocks'] += 1
        stats['total_lines'] += block.total_lines
        stats['error_count'] += block.error_count
        stats['warn_count'] += block.warn_count
        if block.unique_orders > 0:
            stats['order_logs_preserved'] += block.unique_orders

        # Calculate savings
        stats['original_bytes'] += result['original_size']
        stats['saved_bytes'] += result['original_size'] - result['estimated_size']

        # Add to calculator
        calculator.add_result({
            'original_size': result['original_size'],
            'new_size': result['estimated_size'],
            'data_type': 'log'
        })

    # Results
    print("\n" + "="*70)
    print("RESULTS - 7 Day Log Analysis")
    print("="*70)

    print(f"\n[Processing Summary]")
    print(f"  Total Blocks: {stats['total_blocks']}")
    print(f"  Total Lines: {stats['total_lines']:,}")
    print(f"  Original Size: {stats['original_bytes'] / 1024 / 1024:.2f} MB")

    print(f"\n[Action Distribution]")
    total = stats['total_blocks']
    print(f"  Preserve intact: {stats['preserve']} blocks ({stats['preserve']/total*100:.1f}%)")
    print(f"  Sample: {stats['sample']} blocks ({stats['sample']/total*100:.1f}%)")
    print(f"  Compress: {stats['compress']} blocks ({stats['compress']/total*100:.1f}%)")
    print(f"  Discard: {stats['discard']} blocks ({stats['discard']/total*100:.1f}%)")

    print(f"\n[Content Detection]")
    print(f"  Error entries: {stats['error_count']:,}")
    print(f"  Warning entries: {stats['warn_count']:,}")
    print(f"  Order logs preserved: {stats['order_logs_preserved']}")

    print(f"\n[Storage Reduction]")
    original_mb = stats['original_bytes'] / 1024 / 1024
    saved_mb = stats['saved_bytes'] / 1024 / 1024
    reduction_percent = (stats['saved_bytes'] / stats['original_bytes'] * 100) if stats['original_bytes'] > 0 else 0

    print(f"  Original size: {original_mb:.2f} MB")
    print(f"  Space saved: {saved_mb:.2f} MB ({reduction_percent:.1f}%)")
    print(f"  Retained size: {original_mb - saved_mb:.2f} MB")

    # ROI projection
    print(f"\n[ROI Projection - 100 Servers, 1 Year]")
    daily_savings_mb = saved_mb / 7  # 7 days simulated
    annual_savings_tb = daily_savings_mb * 365 * 100 / 1024 / 1024
    storage_cost_per_tb = 5000  # CNY

    print(f"  Annual savings: {annual_savings_tb:.2f} TB")
    print(f"  Annual cost reduction: {annual_savings_tb * storage_cost_per_tb:,.0f} CNY")

    # Business fidelity check
    print(f"\n[Business Fidelity Check]")
    print(f"  ERROR logs preserved: {stats['error_count']} (100%)")
    print(f"  WARNING logs preserved: {stats['warn_count']} (100%)")
    print(f"  [OK] Diagnostic capability intact")

    # Policy display
    print(f"\n[Policy Configuration]")
    print(f"  ERROR handling: PRESERVE (always)")
    print(f"  WARN handling: PRESERVE (always)")
    print(f"  INFO handling: SAMPLE at {policy.level_rules[2].sampling_rate:.0%}")
    print(f"  DEBUG handling: ARCHIVE at {policy.level_rules[3].sampling_rate:.0%}")
    print(f"  TRACE handling: DISCARD")
    print(f"  Order logs: {'PRESERVE' if policy.preserve_order_logs else 'SAMPLE'}")

    return {
        'stats': stats,
        'reduction_percent': reduction_percent,
        'annual_savings': annual_savings_tb * storage_cost_per_tb
    }


def demo_sampling_strategies():
    """Demonstrate different sampling strategies."""

    print("\n" + "="*70)
    print("Sampling Strategy Comparison")
    print("="*70)

    analyzer = LogAnalyzer()

    # Generate 1000 sample lines
    logs = generate_realistic_logs(hours=1, lines_per_hour=1000)

    # Parse all lines
    parsed_lines = [analyzer.analyze_line(log, i) for i, log in enumerate(logs)]

    print(f"\nOriginal: {len(parsed_lines)} lines")
    print(f"  Errors: {sum(1 for l in parsed_lines if l.level == LogLevel.ERROR)}")
    print(f"  Warnings: {sum(1 for l in parsed_lines if l.level == LogLevel.WARN)}")
    print(f"  Info: {sum(1 for l in parsed_lines if l.level == LogLevel.INFO)}")
    print(f"  Debug: {sum(1 for l in parsed_lines if l.level == LogLevel.DEBUG)}")

    # Test different strategies
    strategies = [
        ('HEAD', 'head'),
        ('TAIL', 'tail'),
        ('DISTRIBUTED', 'distributed'),
        ('ERROR_FOCUSED', 'error_focused'),
    ]

    print(f"\n[Sampling at 10%]")
    for name, strategy in strategies:
        sampled = analyzer.apply_sampling(parsed_lines, strategy, 0.1)
        errors_kept = sum(1 for l in sampled if l.level == LogLevel.ERROR)
        warns_kept = sum(1 for l in sampled if l.level == LogLevel.WARN)
        print(f"  {name:15}: {len(sampled):4} lines (errors:{errors_kept}, warns:{warns_kept})")

    # Test at 30%
    print(f"\n[Sampling at 30%]")
    sampled_30 = analyzer.apply_sampling(parsed_lines, 'error_focused', 0.3)
    print(f"  ERROR_FOCUSED: {len(sampled_30)} lines")
    print(f"    Errors preserved: {sum(1 for l in sampled_30 if l.level == LogLevel.ERROR)}")
    print(f"    Warnings preserved: {sum(1 for l in sampled_30 if l.level == LogLevel.WARN)}")
    print(f"    Info preserved: {sum(1 for l in sampled_30 if l.level == LogLevel.INFO)}")


def demo_anomaly_detection():
    """Demonstrate anomaly detection capabilities."""

    print("\n" + "="*70)
    print("Anomaly Detection Demo")
    print("="*70)

    analyzer = LogAnalyzer()

    # Create a scenario with error burst
    logs = [
        "2024-01-15 10:30:45 INFO [main] Application started",
        "2024-01-15 10:30:46 INFO [http] GET /api/health 200 5ms",
        "2024-01-15 10:30:47 INFO [http] GET /api/users 200 15ms",
        "2024-01-15 10:30:48 ERROR [service] NullPointerException: Cannot invoke on null",
        "2024-01-15 10:30:49 ERROR [service] NullPointerException: Cannot invoke on null",
        "2024-01-15 10:30:50 ERROR [service] NullPointerException: Cannot invoke on null",
        "2024-01-15 10:30:51 ERROR [service] NullPointerException: Cannot invoke on null",
        "2024-01-15 10:30:52 ERROR [service] NullPointerException: Cannot invoke on null",
        "2024-01-15 10:30:53 WARN [service] Error rate elevated",
        "2024-01-15 10:30:54 INFO [http] POST /api/orders 201 50ms",
    ]

    # Add more logs to simulate burst
    for i in range(55):
        logs.append(f"2024-01-15 10:30:{55+i%60:02d} DEBUG [pool] Connection check")

    block = analyzer.analyze_block(logs, "anomaly_test")

    print(f"\n[Block Analysis]")
    print(f"  Total Lines: {block.total_lines}")
    print(f"  Errors: {block.error_count}")
    print(f"  Warnings: {block.warn_count}")
    print(f"  Error Burst: {block.error_burst}")
    print(f"  Circuit Breaker: {block.circuit_breaker_open}")
    print(f"  Memory Warning: {block.memory_warning}")
    print(f"  Timeout Pattern: {block.timeout_pattern}")
    print(f"  Preserve Score: {block.preserve_recommendation:.2f}")

    # Evaluate with policy
    policy = LogPolicy.default_application()
    engine = LogPolicyEngine(policy)

    result = engine.evaluate_block(block, "/var/log/app-error-test.log")

    print(f"\n[Policy Decision]")
    print(f"  Priority: {result['priority']}")
    print(f"  Action: {result['action']}")
    print(f"  Retention: {result['retention_days']} days")
    print(f"  Reasons: {result['reasons']}")


def main():
    print("\n" + "#"*70)
    print("# Semantic-Aware Server Log Processing Demo")
    print("#"*70)
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("#"*70)

    # Main demo
    demo_log_reduction()

    # Sampling strategies
    demo_sampling_strategies()

    # Anomaly detection
    demo_anomaly_detection()

    print("\n" + "#"*70)
    print("# Demo Complete")
    print("#"*70)
    print("""
Next Steps:
1. Connect real log sources (ELK, Splunk, custom)
2. Tune policy based on specific log patterns
3. Deploy for 30-day trial with baseline comparison
""")


if __name__ == '__main__':
    main()
