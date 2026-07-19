#!/usr/bin/env node
// Pre-tool safety hook: blocks destructive Azure / filesystem operations.
// Reads the tool input from stdin as JSON and emits a PreToolUse permission decision.
// Cross-platform (Node): no bash/python3 dependency.
//
// These agents are meant to AUDIT and DESIGN (read-only + generate artifacts).
// Any command that could delete cloud resources, remove audit logging, or tear
// down guardrails is blocked here and must be run by a human explicitly.

const BLOCKED_PATTERNS = [
  /rm\s+-rf/i,
  /rm\s+-r\b/i,
  /rmdir/i,
  // Azure resource destruction
  /az\s+group\s+delete/i,
  /az\s+resource\s+delete/i,
  /az\s+storage\s+account\s+delete/i,
  /az\s+keyvault\s+(delete|purge)/i,
  /az\s+synapse\s+workspace\s+delete/i,
  /az\s+sql\s+(server|db|mi)\s+delete/i,
  /az\s+cosmosdb\s+delete/i,
  /az\s+eventhubs?\s+namespace\s+delete/i,
  // Removing audit logging or governance guardrails
  /az\s+monitor\s+diagnostic-settings\s+delete/i,
  /az\s+policy\s+(assignment|definition)\s+delete/i,
  /az\s+role\s+assignment\s+delete/i,
  // Identity / session teardown
  /az\s+ad\s+(app|sp)\s+delete/i,
  /az\s+account\s+clear/i,
  // Generic SQL/data destruction (in case of embedded queries)
  /DROP\s+TABLE/i,
  /DROP\s+DATABASE/i,
  /TRUNCATE\s+TABLE/i,
];

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);

let command = '';
try {
  const data = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
  command = data?.tool_input?.command ?? '';
} catch {
  command = '';
}

for (const pattern of BLOCKED_PATTERNS) {
  if (pattern.test(command)) {
    process.stdout.write(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason:
          `Blocked destructive operation matching /${pattern.source}/. ` +
          `These agents audit and design only — run destructive Azure commands yourself, deliberately.`,
      },
    }));
    process.exit(0);
  }
}

// No match: stay silent and defer to the normal permission flow.
process.exit(0);
