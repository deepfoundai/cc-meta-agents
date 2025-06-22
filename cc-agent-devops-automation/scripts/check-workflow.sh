#!/bin/bash
# Check the latest workflow run
WORKFLOW="update-registry.yml"
REPO="deepfoundai/cc-agent-doc-registry"

echo "🔍 Checking latest run of $WORKFLOW..."

LATEST_RUN=$(gh run list --repo "$REPO" --workflow "$WORKFLOW" --limit 1 --json status,conclusion,createdAt,url)

if [ -z "$LATEST_RUN" ] || [ "$LATEST_RUN" = "[]" ]; then
    echo "No workflow runs found"
    exit 0
fi

STATUS=$(echo "$LATEST_RUN" | jq -r '.[0].status')
CONCLUSION=$(echo "$LATEST_RUN" | jq -r '.[0].conclusion')
CREATED_AT=$(echo "$LATEST_RUN" | jq -r '.[0].createdAt')
URL=$(echo "$LATEST_RUN" | jq -r '.[0].url')

echo "Status: $STATUS"
echo "Conclusion: $CONCLUSION"
echo "Created: $CREATED_AT"
echo "URL: $URL"

if [ "$CONCLUSION" = "failure" ]; then
    echo "⚠️  Workflow failed! Creating issue..."
    gh issue create \
        --repo "$REPO" \
        --title "Workflow failure: $WORKFLOW" \
        --body "The $WORKFLOW workflow failed at $CREATED_AT. 

View the run: $URL

Please investigate and fix the issue." \
        --label "bug,automation"
    echo "✅ Issue created"
elif [ "$CONCLUSION" = "success" ]; then
    echo "✅ Workflow completed successfully"
else
    echo "ℹ️  Workflow is $STATUS"
fi