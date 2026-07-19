#!/usr/bin/env node
// Session end hook: archives a short session activity summary.
// Cross-platform (Node): paths resolved from CLAUDE_PROJECT_DIR, no hardcoded machine paths.

import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectDir =
  process.env.CLAUDE_PROJECT_DIR ??
  resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

const pad = (n) => String(n).padStart(2, '0');
const now = new Date();
const timestamp =
  `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
  `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
const fileStamp =
  `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-` +
  `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;

const logDir = join(projectDir, 'reports', 'output', 'session-logs');
mkdirSync(logDir, { recursive: true });
const logFile = join(logDir, `session-${fileStamp}.log`);

const lines = [
  `Session ended: ${timestamp}`,
  `Project: Azure Agents (Claude Code)`,
  `Working dir: ${projectDir}`,
];
writeFileSync(logFile, lines.join('\n') + '\n');
