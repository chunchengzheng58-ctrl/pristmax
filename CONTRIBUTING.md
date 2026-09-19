# Contributing to Pristmax

Thank you for your interest in contributing to Pristmax!

## How to Contribute

### Reporting Bugs

1. Check if the bug is already reported in [Issues](../../issues)
2. If not, create a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Your environment (OS, Python version, etc.)

### Suggesting Features

1. Search existing issues first
2. Open a new issue with `[Feature Request]` prefix
3. Describe the use case and benefits

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests if available
5. Commit with clear messages
6. Push and create PR

### Code Style

- Follow PEP 8
- Add docstrings for new functions
- Keep functions focused and small

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/pristmax.git
cd pristmax

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py --host 0.0.0.0 --port 5000
```

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
