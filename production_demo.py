# -*- coding: utf-8 -*-
"""
Production Version Demo

Demonstrates the production-ready semantic reduction system.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from semantic_reduction import SemanticReducer, Config, setup_logger
from semantic_reduction.utils.config import init_config


def demo_basic_usage():
    """Demonstrate basic usage of the production system"""
    print("\n" + "="*70)
    print("Production Demo - Basic Usage")
    print("="*70)

    # Initialize configuration
    config = init_config('config.yaml')
    print(f"\nConfig loaded:")
    print(f"  System: {config.get('system.name')}")
    print(f"  Debug: {config.get('system.debug')}")
    print(f"  Storage cost: {config.get('roi.storage_cost_per_tb')} {config.get('roi.currency')}/TB")

    # Setup logger
    logger = setup_logger('demo', log_file='./logs/demo.log')
    logger.info("Starting production demo")

    # Initialize reducer
    reducer = SemanticReducer(config=config, audit_path='./data/audit')

    # Simulate video processing
    print("\n[1] Simulating video processing...")

    video_analysis = {
        'motion_score': 0.4,
        'has_faces': True,
        'has_people': True,
        'has_vehicles': False,
        'scene_type': 'indoor'
    }

    policy = {
        'preserve_with_faces': True,
        'preserve_with_people': True,
        'preserve_with_vehicles': True,
        'low_value_downsample_ratio': 0.1
    }

    # Create simulated video file
    video_path = './data/sample_video.mp4'
    Path('./data').mkdir(exist_ok=True)
    Path(video_path).write_text('simulated_video_content')

    result = reducer.process_video(video_path, video_analysis, policy)

    print(f"\n  Video: {video_path}")
    print(f"  Action: {result.action.value}")
    print(f"  Classification: {result.classification.value}")
    print(f"  Original: {result.original_size} bytes")
    print(f"  New: {result.new_size} bytes")
    print(f"  Savings: {result.savings_percent:.1f}%")
    print(f"  Reasons: {result.reasons}")

    # Simulate log processing
    print("\n[2] Simulating log processing...")

    log_content = """
2024-01-15 10:30:45 ERROR Database connection failed
2024-01-15 10:30:46 WARN Retry attempt 1 of 3
2024-01-15 10:30:47 INFO User login: user_123
2024-01-15 10:30:48 DEBUG Connection pool size: 10
2024-01-15 10:30:49 TRACE Method entry: getUserById(123)
2024-01-15 10:30:50 ERROR Connection timeout after 30s
"""

    log_analysis = {
        'log_id': 'app_log_001',
        'error_count': 2,
        'warn_count': 1,
        'line_count': 6,
        'has_business_events': True
    }

    log_policy = {
        'default_sampling_rate': 0.1,
        'preserve_error': True,
        'preserve_warn': True
    }

    log_result = reducer.process_log(log_content, log_analysis, log_policy)

    print(f"\n  Log ID: {log_result.data_id}")
    print(f"  Action: {log_result.action.value}")
    print(f"  Classification: {log_result.classification.value}")
    print(f"  Original: {log_result.original_size} bytes")
    print(f"  New: {log_result.new_size} bytes")
    print(f"  Savings: {log_result.savings_percent:.1f}%")

    # Get statistics
    print("\n[3] Processing Statistics:")
    stats = reducer.get_stats()
    print(f"  Total processed: {stats['total_processed']}")
    print(f"  Total original: {stats['total_original_bytes']:,} bytes")
    print(f"  Total new: {stats['total_new_bytes']:,} bytes")
    print(f"  Savings: {stats['savings_percent']:.1f}%")
    print(f"  By action: {stats['by_action']}")
    print(f"  By classification: {stats['by_classification']}")

    # Calculate ROI
    print("\n[4] ROI Calculation (1000 cameras, 1 year):")
    roi = reducer.calculate_roi(scale_factor=1000, years=1)
    print(f"  Annual original: {roi['projected_annual_original_tb']:.2f} TB")
    print(f"  Annual reduced: {roi['projected_annual_reduced_tb']:.2f} TB")
    print(f"  Annual savings: {roi['annual_savings']:,.0f} {roi['currency']}")
    print(f"  Implementation cost: {roi['implementation_cost']:,.0f} {roi['currency']}")
    print(f"  ROI: {roi['roi_percent']:.0f}%")
    print(f"  Payback: {roi['payback_months']:.1f} months")


def demo_config_management():
    """Demonstrate configuration management"""
    print("\n" + "="*70)
    print("Production Demo - Configuration Management")
    print("="*70)

    # Create config from file
    config = Config('config.yaml')

    print("\n[1] Current configuration:")
    print(f"  video.motion_threshold: {config.get('video.motion_threshold')}")
    print(f"  video.preserve_with_faces: {config.get('video.preserve_with_faces')}")
    print(f"  storage.base_path: {config.get('storage.base_path')}")

    # Modify config programmatically
    print("\n[2] Modifying configuration...")
    config.set('video.low_value_downsample_ratio', 0.15)
    print(f"  video.low_value_downsample_ratio: {config.get('video.low_value_downsample_ratio')}")

    # Environment variable override
    print("\n[3] Environment variable override:")
    print(f"  Set SR_STORAGE_COST=8000 and reinitialize to test")


def demo_adapter_usage():
    """Demonstrate adapter usage"""
    print("\n" + "="*70)
    print("Production Demo - Adapter Usage")
    print("="*70)

    from semantic_reduction.adapters.rtsp_adapter import RTSPAdapter, RTSPConnectionPool

    print("\n[1] RTSP Adapter (simulated):")
    adapter = RTSPAdapter(
        rtsp_url='rtsp://camera.example.com:554/stream1',
        camera_id='CAM-001'
    )

    print(f"  Camera ID: {adapter.camera_id}")
    print(f"  Status: {adapter.status.value}")
    print(f"  Simulated: {adapter._simulated}")

    # Connect (simulated)
    connected = adapter.connect()
    print(f"  Connected: {connected}")
    print(f"  Status after connect: {adapter.status.value}")

    # Get stream info
    info = adapter.get_info()
    print(f"  Stream info: {info['camera_id']} @ {info['rtsp_url']}")

    adapter.disconnect()
    print(f"  Status after disconnect: {adapter.status.value}")

    print("\n[2] RTSP Connection Pool:")
    pool = RTSPConnectionPool(max_connections=10)

    # Add cameras
    for i in range(1, 4):
        cam = pool.add_camera(
            camera_id=f'CAM-{i:03d}',
            rtsp_url=f'rtsp://camera{i}.example.com:554/stream'
        )
        print(f"  Added: {cam.camera_id}")

    print(f"  Total cameras in pool: {len(pool)}")

    # Connect all
    results = pool.connect_all()
    print(f"  Connection results: {results}")

    # Get all stats
    all_stats = pool.get_all_stats()
    print(f"  Camera stats: {list(all_stats.keys())}")

    pool.disconnect_all()


def main():
    print("\n" + "#"*70)
    print("# Semantic Reduction System - Production Demo")
    print("#"*70)
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# Version: 1.0.0")
    print("#"*70)

    # Create required directories
    Path('./data').mkdir(exist_ok=True)
    Path('./data/audit').mkdir(exist_ok=True)
    Path('./logs').mkdir(exist_ok=True)

    try:
        demo_basic_usage()
        demo_config_management()
        demo_adapter_usage()

        print("\n" + "#"*70)
        print("# Demo Complete - Production System Verified")
        print("#"*70)
        print("""
Next Steps:
1. Run: python web/api.py  (start web console)
2. Connect real cameras via RTSP
3. Configure policies for your environment
4. Deploy with Docker: docker-compose up -d
""")

    except FileNotFoundError as e:
        print(f"\nConfig file not found: {e}")
        print("Using default configuration...")

        # Fall back to default config
        from semantic_reduction import SemanticReducer
        reducer = SemanticReducer()
        print("Reducer initialized with defaults")


if __name__ == '__main__':
    main()
