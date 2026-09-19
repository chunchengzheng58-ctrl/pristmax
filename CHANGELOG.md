# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.1.0] - 2026-09-19

### Added
- **MCP Server**: New Model Context Protocol server for AI integration
  - 8 tools: storage_stats, storage_large_files, storage_duplicates, storage_suggestions, storage_analyze, storage_chat, storage_cleanup_duplicates, storage_cleanup_large
  - stdio mode for Claude Code integration
  - HTTP mode for API access (port 5003)
- AI Integration section in README
- Claude Desktop configuration template

### Changed
- Updated README with MCP Server documentation

## [1.0.0] - 2026-09-18

### Added
- **Storage Agent CLI**: Full-featured command-line tool
  - `--stats` with progress bar
  - `--suggest` for intelligent recommendations
  - `--chat` for natural language interaction
  - `--monitor` for continuous directory watching
  - `--cleanup-duplicates` and `--cleanup-large` with dry-run/execute support
- **Incremental Scanning**: SQLite cache for faster re-scans
- **Export Reports**: HTML and JSON report generation
- **Open Source Philosophy**: Clear licensing boundary
- Claude contributor (Huaichuns) on GitHub

### Features
- File deduplication detection
- Large file identification
- Storage category analysis (code, documents, images, videos, archives, etc.)
- Natural language query interface
- Safe cleanup with preview mode

## [0.1.0] - 2026-09-17

### Added
- Initial project structure
- Web console UI
- REST API server
- Authentication system
- Storage backend adapters (Local, NAS, Cloud)
- Task scheduler
- Marketing website
