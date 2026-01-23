export interface PromptAnalysis {
  characterCount: number;
  category: 'empty' | 'short' | 'medium' | 'long';
  label: string;
  color: 'default' | 'success' | 'warning' | 'error' | 'info';
}

export interface PromptThresholds {
  short: number;
  medium: number;
  long: number;
}

// Single source of truth for prompt character thresholds
export const PROMPT_THRESHOLDS: PromptThresholds = {
  short: 100,
  medium: 500,
  long: 500, // This represents the minimum for long category
} as const;

/**
 * Analyzes a prompt string and returns character count, category, label, and color
 * This is the single source of truth for prompt classification across the application
 */
export function analyzePrompt(prompt: string): PromptAnalysis {
  const characterCount = prompt?.length || 0;

  if (characterCount === 0) {
    return {
      characterCount: 0,
      category: 'empty',
      label: 'Empty',
      color: 'error',
    };
  }

  if (characterCount < PROMPT_THRESHOLDS.short) {
    return {
      characterCount,
      category: 'short',
      label: 'Short',
      color: 'success',
    };
  }

  if (characterCount < PROMPT_THRESHOLDS.medium) {
    return {
      characterCount,
      category: 'medium',
      label: 'Medium',
      color: 'warning',
    };
  }

  return {
    characterCount,
    category: 'long',
    label: 'Long',
    color: 'error',
  };
}

/**
 * Gets the character count display text
 */
export function getCharacterCountText(characterCount: number): string {
  return `${characterCount} character${characterCount !== 1 ? 's' : ''}`;
}

/**
 * Gets the abbreviated character count display text for compact views
 */
export function getCharacterCountTextShort(characterCount: number): string {
  return `${characterCount} chars`;
}

/**
 * Truncates a prompt to a specified length with ellipsis
 */
export function truncatePrompt(prompt: string, maxLength: number = 120): string {
  if (!prompt || prompt.length <= maxLength) return prompt || '';
  return prompt.substring(0, maxLength) + '...';
}

/**
 * Checks if a prompt should be considered long for display purposes
 */
export function isLongPrompt(prompt: string): boolean {
  return analyzePrompt(prompt).category === 'long';
}

/**
 * Gets a human-readable description of the prompt length thresholds
 */
export function getPromptThresholdDescription(): string {
  return `Short: < ${PROMPT_THRESHOLDS.short} chars, Medium: ${PROMPT_THRESHOLDS.short}-${PROMPT_THRESHOLDS.medium - 1} chars, Long: ≥ ${PROMPT_THRESHOLDS.medium} chars`;
}
