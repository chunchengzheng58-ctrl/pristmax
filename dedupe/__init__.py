"""Deduplication Module - Kafka consumer workers for distributed dedup"""

# This module contains Kafka consumer workers that process dedup events
# See pipeline.py for the main dedup engine
# See kafka_integration.py for Kafka producer/consumer
# See bloom_sync.py for bloom filter synchronization
# See lmdb_cache.py for local LMDB cache
