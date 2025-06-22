# Contributing to CC Agent Routing Manager

## Development Setup

### Prerequisites
- Python 3.11 or higher
- AWS SAM CLI
- Docker (for local testing)
- AWS credentials configured

### Local Development
1. Clone the repository
2. Install dependencies:
   ```bash
   make install
   ```
3. Run tests:
   ```bash
   make test
   ```
4. Run linting:
   ```bash
   make lint
   ```

## Code Standards

### Python Style
- Follow PEP 8
- Use type hints for all functions
- Maximum line length: 100 characters
- Use Black for formatting

### Testing Requirements
- Maintain >80% code coverage
- Write unit tests for all new functions
- Include integration tests for API endpoints
- Mock external services appropriately

### Documentation
- Update README.md for new features
- Document all public functions with docstrings
- Include examples in docstrings where helpful

## Development Workflow

### 1. Feature Development
1. Create feature branch: `feature/routing-<feature-name>`
2. Write tests first (TDD approach)
3. Implement feature
4. Ensure all tests pass
5. Update documentation

### 2. Testing
```bash
# Run all tests
make test

# Run specific test file
pytest tests/test_handler.py

# Run with coverage
pytest --cov=src --cov-report=html
```

### 3. Local Testing
```bash
# Start local API
make local-test

# Test endpoints
curl http://localhost:3000/health
```

### 4. Deployment
```bash
# Deploy to dev
make deploy ENV=dev

# Run smoke tests
make smoke-test ENV=dev
```

## Adding New Agents

To add support for a new agent:

1. Update `ROUTING_PATTERNS` in `handler.py`:
   ```python
   ROUTING_PATTERNS = {
       'new-agent': [
           r'pattern1|pattern2',
           r'complex.*pattern'
       ]
   }
   ```

2. Add agent endpoint to `template.yaml`:
   ```yaml
   AGENT_ENDPOINTS: !Sub |
     {
       "new-agent": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:cc-agent-new-${Environment}"
     }
   ```

3. Write tests for new routing patterns
4. Update documentation

## Error Handling

- Always use structured logging
- Include request IDs in error messages
- Implement retry logic for transient failures
- Use circuit breaker pattern for agent failures

## Performance Considerations

- Keep Lambda cold start time minimal
- Use connection pooling for DynamoDB
- Implement caching where appropriate
- Monitor and optimize routing decision time

## Security

- Never log sensitive data
- Validate all input data
- Use IAM roles for inter-service communication
- Follow least privilege principle

## Pull Request Process

1. Ensure all tests pass
2. Update documentation
3. Add entry to CHANGELOG.md
4. Request review from team lead
5. Squash commits before merge

## Questions?

Contact the CreativeCloud infrastructure team.