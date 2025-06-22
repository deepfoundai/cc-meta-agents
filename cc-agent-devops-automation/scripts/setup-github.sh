#!/bin/bash
set -e

echo "🔧 Setting up GitHub repository configurations..."

REPO="deepfoundai/cc-agent-doc-registry"

# 1. Enable branch protection on main
echo "🔒 Configuring branch protection for main..."
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "/repos/${REPO}/branches/main/protection" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=update-registry" \
  -f "required_pull_request_reviews[required_approving_review_count]=1" \
  -f "required_pull_request_reviews[dismiss_stale_reviews]=true" \
  -f "enforce_admins=false" \
  -f "restrictions=null" \
  -f "allow_force_pushes=false" \
  -f "allow_deletions=false"

# 2. Verify dependabot configuration
echo "📦 Checking Dependabot configuration..."
if gh api "/repos/${REPO}/contents/.github/dependabot.yml" >/dev/null 2>&1; then
    echo "✅ Dependabot configuration exists"
else
    echo "⚠️  Creating Dependabot configuration..."
    cat > /tmp/dependabot.yml << 'EOF'
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
    labels:
      - "dependencies"
      - "security"
    open-pull-requests-limit: 5
    
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
    labels:
      - "dependencies"
      - "maintenance"
EOF
    
    # Create the file via API
    CONTENT=$(base64 < /tmp/dependabot.yml)
    gh api \
      --method PUT \
      -H "Accept: application/vnd.github+json" \
      "/repos/${REPO}/contents/.github/dependabot.yml" \
      -f "message=Add Dependabot configuration" \
      -f "content=${CONTENT}"
fi

# 3. Set up email notifications
echo "📧 Configuring email notifications..."
echo "Note: Email notifications must be configured in personal GitHub settings"
echo "Visit: https://github.com/settings/notifications"
echo "Enable email notifications for:"
echo "  - todd@deepfoundai.com"
echo "  - harvey@deepfoundai.com"

# 4. Create monitoring script
echo "📊 Creating workflow monitoring script..."
cat > /tmp/check-workflow.sh << 'EOF'
#!/bin/bash
# Check the latest workflow run
WORKFLOW="update-registry.yml"
LATEST_RUN=$(gh run list --workflow "$WORKFLOW" --limit 1 --json status,conclusion,createdAt)

if [ -z "$LATEST_RUN" ] || [ "$LATEST_RUN" = "[]" ]; then
    echo "No workflow runs found"
    exit 0
fi

CONCLUSION=$(echo "$LATEST_RUN" | jq -r '.[0].conclusion')
if [ "$CONCLUSION" = "failure" ]; then
    echo "⚠️  Workflow failed! Creating issue..."
    CREATED_AT=$(echo "$LATEST_RUN" | jq -r '.[0].createdAt')
    gh issue create \
        --title "Workflow failure: $WORKFLOW" \
        --body "The $WORKFLOW workflow failed at $CREATED_AT. Please investigate." \
        --label "bug,automation"
fi
EOF

chmod +x /tmp/check-workflow.sh
cp /tmp/check-workflow.sh "$SCRIPT_DIR/check-workflow.sh"

echo "✅ GitHub setup complete!"
echo ""
echo "Next steps:"
echo "1. Verify branch protection: https://github.com/${REPO}/settings/branches"
echo "2. Check Dependabot alerts: https://github.com/${REPO}/security/dependabot"
echo "3. Run workflow check: ./scripts/check-workflow.sh"