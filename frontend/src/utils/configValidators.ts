// TypeScript types and validators matching backend Pydantic schemas exactly

export type AssertionOperator =
  | "STRING_EQUALS"
  | "STRING_CONTAINS"
  | "STRING_NOT_CONTAINS"
  | "STRING_FUZZY_MATCH"
  | "JSON_EQUALS"
  | "JSON_CONTAINS"
  | "JSON_PART_OF"
  | "NUMERIC_MATCH"
  | "BOOL"
  | "ARRAY_LENGTH_MATCH"
  | "ARRAY_STRING_EQUALS"
  | "ARRAY_STRING_CONTAINS"
  | "ARRAY_STRING_NOT_CONTAINS"
  | "ARRAY_NUMERIC_MATCH"
  | "ARRAY_BOOL"
  | "DATETIME_MATCH"
  | "IMAGE_FUZZY_MATCH"
  | "IMAGE_CONTENT_LLM_MATCH";

export interface Assertion {
  operator: AssertionOperator;
  expected?: (string | number | boolean)[];
  path_to_actual?: string;
  paths_to_expected?: string[];
}

export interface ExpectedStateFunction {
  function: string;
  args?: Record<string, unknown>;
}

export interface ExtractStatesConfig {
  expected_state_functions: ExpectedStateFunction[];
}

export interface StateGraderConfig {
  path_to_actual?: string;
  assertions: Assertion[];
}

export interface TextGraderConfig {
  assertions: Assertion[];
}

export interface LlmGraderConfig {
  instruction: string;
  include_trajectory?: boolean;
  model?: string;
}

export interface GraderConfig {
  extract_states_config?: ExtractStatesConfig;
  state_grader_configs?: StateGraderConfig[];
  answer_grader_config?: TextGraderConfig;
  url_grader_config?: TextGraderConfig;
  llm_grader_configs?: LlmGraderConfig[];
}

export interface SimulatorConfig {
  seed_data?: Record<string, unknown>;
  setup_type?: string;
  user_context?: Record<string, unknown>;
  date_override?: Record<string, unknown>;
}

export interface TaskConfig {
  grader_config?: GraderConfig | null;
  simulator_config?: SimulatorConfig | null;
}

// Validation functions

export function validateAssertionOperator(operator: string): operator is AssertionOperator {
  const validOperators: AssertionOperator[] = [
    "STRING_EQUALS",
    "STRING_CONTAINS",
    "STRING_NOT_CONTAINS",
    "STRING_FUZZY_MATCH",
    "JSON_EQUALS",
    "JSON_CONTAINS",
    "JSON_PART_OF",
    "NUMERIC_MATCH",
    "BOOL",
    "ARRAY_LENGTH_MATCH",
    "ARRAY_STRING_EQUALS",
    "ARRAY_STRING_CONTAINS",
    "ARRAY_STRING_NOT_CONTAINS",
    "ARRAY_NUMERIC_MATCH",
    "ARRAY_BOOL",
    "DATETIME_MATCH",
    "IMAGE_FUZZY_MATCH",
    "IMAGE_CONTENT_LLM_MATCH",
  ];
  return validOperators.includes(operator as AssertionOperator);
}

export function validateAssertion(assertion: unknown): string | null {
  if (!assertion || typeof assertion !== "object" || Array.isArray(assertion)) {
    return "Assertion must be an object";
  }

  const a = assertion as Record<string, unknown>;

  // Validate operator (required)
  if (!a.operator || typeof a.operator !== "string") {
    return "Assertion must have a valid 'operator' field (string)";
  }
  if (!validateAssertionOperator(a.operator)) {
    return `Invalid operator: ${a.operator}. Must be one of the supported assertion operators.`;
  }

  // Validate expected (optional)
  if (a.expected !== undefined) {
    if (!Array.isArray(a.expected)) {
      return "Assertion 'expected' must be an array if provided";
    }
  }

  // Validate path_to_actual (optional)
  if (a.path_to_actual !== undefined) {
    if (typeof a.path_to_actual !== "string") {
      return "Assertion 'path_to_actual' must be a string if provided";
    }
  }

  // Validate paths_to_expected (optional)
  if (a.paths_to_expected !== undefined) {
    if (!Array.isArray(a.paths_to_expected)) {
      return "Assertion 'paths_to_expected' must be an array if provided";
    }
    // Check each entry is a non-empty string
    for (const path of a.paths_to_expected) {
      if (typeof path !== "string" || path.trim() === "") {
        return "Assertion 'paths_to_expected' entries must be non-empty strings";
      }
    }
  }

  // Check for unknown fields (extra = "forbid")
  const allowedFields = ["operator", "expected", "path_to_actual", "paths_to_expected"];
  const unknownFields = Object.keys(a).filter((k) => !allowedFields.includes(k));
  if (unknownFields.length > 0) {
    return `Unknown fields in assertion: ${unknownFields.join(", ")}`;
  }

  return null;
}

export function validateExpectedStateFunction(func: unknown): string | null {
  if (!func || typeof func !== "object" || Array.isArray(func)) {
    return "Expected state function must be an object";
  }

  const f = func as Record<string, unknown>;

  // Validate function (required)
  if (!f.function || typeof f.function !== "string") {
    return "Expected state function must have a 'function' field (string)";
  }

  // Validate args (optional, defaults to {})
  if (f.args !== undefined) {
    if (typeof f.args !== "object" || Array.isArray(f.args) || f.args === null) {
      return "Expected state function 'args' must be an object if provided";
    }
  }

  // Check for unknown fields
  const allowedFields = ["function", "args"];
  const unknownFields = Object.keys(f).filter((k) => !allowedFields.includes(k));
  if (unknownFields.length > 0) {
    return `Unknown fields in expected state function: ${unknownFields.join(", ")}`;
  }

  return null;
}

export function validateExtractStatesConfig(config: unknown): string | null {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    return "extract_states_config must be an object";
  }

  const c = config as Record<string, unknown>;

  // Validate expected_state_functions (required)
  if (!Array.isArray(c.expected_state_functions)) {
    return "extract_states_config must have 'expected_state_functions' array";
  }

  // Validate each function
  for (let i = 0; i < c.expected_state_functions.length; i++) {
    const error = validateExpectedStateFunction(c.expected_state_functions[i]);
    if (error) {
      return `In expected_state_functions[${i}]: ${error}`;
    }
  }

  // Check for unknown fields
  const allowedFields = ["expected_state_functions"];
  const unknownFields = Object.keys(c).filter((k) => !allowedFields.includes(k));
  if (unknownFields.length > 0) {
    return `Unknown fields in extract_states_config: ${unknownFields.join(", ")}`;
  }

  return null;
}

export function validateStateGraderConfig(config: unknown): string | null {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    return "state_grader_config must be an object";
  }

  const c = config as Record<string, unknown>;

  // Validate assertions (required)
  if (!Array.isArray(c.assertions)) {
    return "state_grader_config must have 'assertions' array";
  }

  // Validate each assertion
  for (let i = 0; i < c.assertions.length; i++) {
    const error = validateAssertion(c.assertions[i]);
    if (error) {
      return `In assertions[${i}]: ${error}`;
    }
  }

  // Validate path_to_actual (optional)
  if (c.path_to_actual !== undefined && typeof c.path_to_actual !== "string") {
    return "state_grader_config 'path_to_actual' must be a string if provided";
  }

  // Check for unknown fields
  const allowedFields = ["path_to_actual", "assertions"];
  const unknownFields = Object.keys(c).filter((k) => !allowedFields.includes(k));
  if (unknownFields.length > 0) {
    return `Unknown fields in state_grader_config: ${unknownFields.join(", ")}`;
  }

  return null;
}

export function validateTextGraderConfig(config: unknown): string | null {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    return "text_grader_config must be an object";
  }

  const c = config as Record<string, unknown>;

  // Validate assertions (required)
  if (!Array.isArray(c.assertions)) {
    return "text_grader_config must have 'assertions' array";
  }

  // Validate each assertion
  for (let i = 0; i < c.assertions.length; i++) {
    const error = validateAssertion(c.assertions[i]);
    if (error) {
      return `In assertions[${i}]: ${error}`;
    }
  }

  // Check for unknown fields
  const allowedFields = ["assertions"];
  const unknownFields = Object.keys(c).filter((k) => !allowedFields.includes(k));
  if (unknownFields.length > 0) {
    return `Unknown fields in text_grader_config: ${unknownFields.join(", ")}`;
  }

  return null;
}

export function validateLlmGraderConfig(config: unknown): string | null {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    return "llm_grader_config must be an object";
  }

  const c = config as Record<string, unknown>;

  // Validate instruction (required)
  if (!c.instruction || typeof c.instruction !== "string") {
    return "llm_grader_config must have 'instruction' field (string)";
  }

  // Validate include_trajectory (optional)
  if (c.include_trajectory !== undefined && typeof c.include_trajectory !== "boolean") {
    return "llm_grader_config 'include_trajectory' must be a boolean if provided";
  }

  // Validate model (optional)
  if (c.model !== undefined && typeof c.model !== "string") {
    return "llm_grader_config 'model' must be a string if provided";
  }

  // Check for unknown fields
  const allowedFields = ["instruction", "include_trajectory", "model"];
  const unknownFields = Object.keys(c).filter((k) => !allowedFields.includes(k));
  if (unknownFields.length > 0) {
    return `Unknown fields in llm_grader_config: ${unknownFields.join(", ")}`;
  }

  return null;
}

export function validateGraderConfig(config: unknown): string | null {
  if (!config || typeof config !== "object" || Array.isArray(config)) {
    return "grader_config must be an object";
  }

  const c = config as Record<string, unknown>;

  // Validate extract_states_config (optional)
  if (c.extract_states_config !== undefined && c.extract_states_config !== null) {
    const error = validateExtractStatesConfig(c.extract_states_config);
    if (error) {
      return `In extract_states_config: ${error}`;
    }
  }

  // Validate state_grader_configs (optional, can be empty array or list)
  if (c.state_grader_configs !== undefined && c.state_grader_configs !== null) {
    // Normalize empty arrays to null (matching backend validator)
    if (Array.isArray(c.state_grader_configs) && c.state_grader_configs.length === 0) {
      // This is valid, but we'll validate the structure anyway
    } else if (!Array.isArray(c.state_grader_configs)) {
      return "state_grader_configs must be an array if provided";
    } else {
      // Validate each state_grader_config
      for (let i = 0; i < c.state_grader_configs.length; i++) {
        const error = validateStateGraderConfig(c.state_grader_configs[i]);
        if (error) {
          return `In state_grader_configs[${i}]: ${error}`;
        }
      }
    }
  }

  // Validate answer_grader_config (optional)
  if (c.answer_grader_config !== undefined && c.answer_grader_config !== null) {
    const error = validateTextGraderConfig(c.answer_grader_config);
    if (error) {
      return `In answer_grader_config: ${error}`;
    }
  }

  // Validate url_grader_config (optional)
  if (c.url_grader_config !== undefined && c.url_grader_config !== null) {
    const error = validateTextGraderConfig(c.url_grader_config);
    if (error) {
      return `In url_grader_config: ${error}`;
    }
  }

  // Validate llm_grader_configs (optional, can be empty array or list)
  if (c.llm_grader_configs !== undefined && c.llm_grader_configs !== null) {
    // Normalize empty arrays to null (matching backend validator)
    if (Array.isArray(c.llm_grader_configs) && c.llm_grader_configs.length === 0) {
      // This is valid, but we'll validate the structure anyway
    } else if (!Array.isArray(c.llm_grader_configs)) {
      return "llm_grader_configs must be an array if provided";
    } else {
      // Validate each llm_grader_config
      for (let i = 0; i < c.llm_grader_configs.length; i++) {
        const error = validateLlmGraderConfig(c.llm_grader_configs[i]);
        if (error) {
          return `In llm_grader_configs[${i}]: ${error}`;
        }
      }
    }
  }

  // Check for unknown fields
  const allowedFields = [
    "extract_states_config",
    "state_grader_configs",
    "answer_grader_config",
    "url_grader_config",
    "llm_grader_configs",
  ];
  const unknownFields = Object.keys(c).filter((k) => !allowedFields.includes(k));
  if (unknownFields.length > 0) {
    return `Unknown fields in grader_config: ${unknownFields.join(", ")}`;
  }

  return null;
}

export function validateTaskConfig(config: unknown): { valid: boolean; errors: { grader_config?: string } } {
  const errors: { grader_config?: string } = {};

  if (!config || typeof config !== "object" || Array.isArray(config)) {
    return {
      valid: false,
      errors: { grader_config: "Task config must be an object with 'grader_config' and/or 'simulator_config' keys" },
    };
  }

  const c = config as Record<string, unknown>;

  // Validate grader_config if present
  if (c.grader_config !== undefined && c.grader_config !== null) {
    const error = validateGraderConfig(c.grader_config);
    if (error) {
      errors.grader_config = error;
    }
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
  };
}
