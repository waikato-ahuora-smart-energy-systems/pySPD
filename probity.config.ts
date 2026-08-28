import { defineConfig, enforceTdd } from '@nizos/probity'
import type { Agent, Verdict } from '@nizos/probity'
import { Codex } from '@openai/codex-sdk'

const codex = new Codex()

const tddValidator: Agent = {
  reason: async (prompt): Promise<Verdict> => {
    try {
      const thread = codex.startThread({
        model: 'gpt-5.4',
        modelReasoningEffort: 'medium',
        skipGitRepoCheck: true,
        sandboxMode: 'read-only',
        approvalPolicy: 'never',
        networkAccessEnabled: false,
        webSearchEnabled: false,
      })
      const turn = await thread.run(prompt)
      const verdict: unknown = JSON.parse(turn.finalResponse)

      if (
        typeof verdict === 'object' &&
        verdict !== null &&
        'kind' in verdict &&
        (verdict.kind === 'pass' || verdict.kind === 'violation') &&
        'reason' in verdict &&
        typeof verdict.reason === 'string'
      ) {
        return { kind: verdict.kind, reason: verdict.reason }
      }

      return {
        kind: 'violation',
        reason: 'Probity validator returned an invalid verdict shape.',
      }
    } catch (error) {
      return {
        kind: 'violation',
        reason: error instanceof Error ? error.message : String(error),
      }
    }
  },
}

export default defineConfig({
  ai: tddValidator,
  rules: [
    {
      files: [
        'src/**',
        'pyspd/**',
        'pySPD/**',
        'test/**',
        'tests/**',
        'tools/**',
      ],
      rules: [enforceTdd()],
    },
  ],
})
