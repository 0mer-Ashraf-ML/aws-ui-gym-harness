import {
  TextField,
  Button,
  Box,
  Typography,
  Chip,
  Collapse,
  IconButton,
  CircularProgress,
  Popover,
  Paper,
} from "@mui/material";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import Editor from "@monaco-editor/react";
import { Formik, Form, Field } from "formik";
import type { FieldProps } from "formik";
import * as Yup from "yup";
import { useState, useEffect, useRef } from "react";
import type React from "react";
import type { Task } from "../types";
import { useCreateTask, useUpdateTask } from "../hooks/useTasks";
import { useGym } from "../hooks/useGyms";
import { analyzePrompt, getCharacterCountText } from "../utils/promptUtils";
import { validateTaskConfig } from "../utils/configValidators";
import SidebarForm from "./SidebarForm";
import { DropzoneArea } from "@seyoon20087/material-ui-dropzone";


interface TaskFormProps {
  open: boolean;
  onClose: () => void;
  task?: Task | null;
  defaultGymId?: string;
  onSuccess?: (task: Task) => void;
  onError?: (error: Error) => void;
}

// Helper function to format JSON string
const formatJson = (value: any): string => {
  if (!value) return "";
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return value; // Return as-is if not valid JSON
    }
  }
  return JSON.stringify(value, null, 2);
};

const VERIFIER_ACCEPTED_FILES = { "text/x-python": [".py"] };

// Create dynamic schema based on whether grader_config is required
const createTaskSchema = (requireGraderConfig: boolean) => {
  return Yup.object().shape({
  task_id: Yup.string()
    .min(3, "Task identifier must be at least 3 characters")
    .max(50, "Task identifier must be less than 50 characters")
    .matches(
      /^[a-zA-Z0-9-_]*$/,
      "Task identifier can only contain letters, numbers, hyphens, and underscores",
    )
    .required("Task identifier is required"),
  prompt: Yup.string()
    .min(10, "Prompt must be at least 10 characters")
    .max(2000, "Prompt must be less than 2000 characters")
    .required("Prompt is required"),
    task_config: Yup.string()
      .test("is-valid-combined-config", function (value: string | undefined) {
        if (!value || value.trim() === "") {
          if (requireGraderConfig) {
            return this.createError({
              message: "Task config is required when gym uses grader_config verification strategy",
            });
          }
          return true;
        }

        try {
          const parsed = JSON.parse(value);

          // Check structure has required keys
          if (requireGraderConfig && !parsed.grader_config) {
            return this.createError({
              message: "grader_config is required in task config when gym uses grader_config verification strategy",
            });
          }

          // Validate against schemas
          const validation = validateTaskConfig(parsed);
          if (!validation.valid) {
            // Format errors more readably
            const errorMessages = Object.entries(validation.errors)
              .map(([key, msg]) => {
                // Clean up field names for better readability
                const cleanKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                return `• ${cleanKey}: ${msg}`;
              })
              .join("\n");
            return this.createError({
              message: `Validation errors found:\n${errorMessages}`,
            });
          }

          return true;
        } catch (error) {
          return this.createError({
            message: `Invalid JSON: ${error instanceof Error ? error.message : "Parse error"}`,
          });
        }
      })
      .when([], {
        is: () => requireGraderConfig,
        then: (schema: Yup.StringSchema) => schema.required("Task config is required"),
      }),
  });
};

export default function TaskForm({
  open,
  onClose,
  task,
  defaultGymId,
  onSuccess,
  onError,
}: TaskFormProps) {
  const createTaskMutation = useCreateTask({
    onSuccess: (createdTask) => {
      onSuccess?.(createdTask);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });
  const updateTaskMutation = useUpdateTask({
    onSuccess: (updatedTask) => {
      onSuccess?.(updatedTask);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });

  const isEditing = !!task;
  const isLoading =
    createTaskMutation.isPending || updateTaskMutation.isPending;

  // Get gym ID from task or defaultGymId
  const gymId = task?.gym_id || defaultGymId || "";
  
  // Fetch gym data to check verification strategy
  const { data: gym, isLoading: isLoadingGym } = useGym(gymId || "");
  
  // Check if grader_config and simulator_config should be shown
  // Both are only relevant when gym uses grader_config verification strategy
  const showGraderConfig = gym?.verification_strategy === "grader_config";

  // Check if verifier script upload widget needs to be shown. Show when:
  // 1. The gym uses verifier_api_script strategy, OR
  // 2. The task already has a verifier_path (when editing)
  const showVerifierFileUpload = 
    gym?.verification_strategy === "verifier_api_script" || 
    (isEditing && !!task?.verifier_path);

  // Collapse state for combined task config
  const [taskConfigExpanded, setTaskConfigExpanded] = useState(false);
  // Popover state for error messages
  const [errorPopoverAnchor, setErrorPopoverAnchor] = useState<HTMLElement | null>(null);

  const [verifierFile, setVerifierFile] = useState<File>();

  // Initialize verifierFilePath from task if editing and task has verifier_path
  const [verifierFilePath, setVerifierFilePath] = useState<string>(task?.verifier_path || "");

  // Debounce timer ref for validation
  const validationTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-expand task_config if gym uses grader_config and config exists
  useEffect(() => {
    if (showGraderConfig && task?.grader_config) {
      setTaskConfigExpanded(true);
    }
  }, [showGraderConfig, task?.grader_config]);

  // Initialize verifierFilePath when task changes (for editing)
  useEffect(() => {
    if (task?.verifier_path) {
      setVerifierFilePath(task.verifier_path);
    } else if (!task) {
      // Reset when creating new task
      setVerifierFilePath("");
    }
  }, [task?.verifier_path, task]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (validationTimeoutRef.current) {
        clearTimeout(validationTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!verifierFile) {
      return;
    }
    
    (async () => {
      try {
        // Append the file to the FormData object with a field name (e.g., 'file')
        const formData = new FormData();
        formData.append('file', verifierFile);
        const API_CONFIG = { // Quick and Dirty
          baseUrl: import.meta.env.VITE_API_URL || "http://localhost:8000",
          disableAuth: import.meta.env.VITE_DISABLE_AUTH === "true",
        } as const;
        const response = await fetch(`${API_CONFIG.baseUrl}/api/v1/tasks/verifier`, {
          method: 'POST',
          body: formData, // The browser automatically sets the correct 'Content-Type': 'multipart/form-data' header, including the boundary
        });
        const result = await response.json();
        setVerifierFilePath(result.file_location);
      } catch (error) {
        console.error('Error uploading file:', error);
      }
    })(); // Immediately invoke the async function
  }, [verifierFile]);

  const initialValues = {
    task_id: task?.task_id || "",
    prompt: task?.prompt || "",
    task_config: formatJson({
      grader_config: task?.grader_config || null,
      simulator_config: task?.simulator_config || null,
    }),
  };

  const handleSubmit = (values: typeof initialValues) => {
    const taskData: any = {
      task_id: values.task_id,
      prompt: values.prompt,
      gym_id: task?.gym_id || defaultGymId || "",
    };
    
    // Only include verifier_path if it's set (either from upload or existing)
    if (verifierFilePath) {
      taskData.verifier_path = verifierFilePath;
    }

    // Parse combined config and extract parts
    if (values.task_config && values.task_config.trim()) {
      try {
        const config = JSON.parse(values.task_config);
        taskData.grader_config = config.grader_config || null;
        taskData.simulator_config = config.simulator_config || null;
      } catch (e) {
        // Should not happen due to validation, but handle gracefully
        console.error("Failed to parse task_config:", e);
        taskData.grader_config = null;
        taskData.simulator_config = null;
      }
    } else {
      taskData.grader_config = null;
      taskData.simulator_config = null;
    }
    
    if (isEditing) {
      updateTaskMutation.mutate({ uuid: task.uuid, ...taskData });
    } else {
      createTaskMutation.mutate(taskData);
    }
  };

  // Create dynamic validation schema based on gym verification strategy
  const taskSchema = createTaskSchema(showGraderConfig);

  return (
    <Formik
      initialValues={initialValues}
      validationSchema={taskSchema}
      onSubmit={handleSubmit}
      enableReinitialize
      validateOnChange={true}
      validateOnBlur={true}
      validateOnMount={false}
    >
      {({ errors, touched, isValid, dirty, values }: {
        errors: Record<string, string | undefined>;
        touched: Record<string, boolean | undefined>;
        isValid: boolean;
        dirty: boolean;
        values: typeof initialValues;
      }) => {
        // Close popover when errors are fixed
        if (!errors.task_config && errorPopoverAnchor) {
          setErrorPopoverAnchor(null);
        }
        
        return (
          <SidebarForm
            open={open}
            onClose={onClose}
            title={isEditing ? "Edit Task" : "Create New Task"}
            width={520}
            disableBackdropClick={isLoading}
            actions={
              <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
                <Button
                  onClick={onClose}
                  disabled={isLoading}
                  variant="outlined"
                  size="large"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  form="task-form"
                  variant="contained"
                  disabled={isLoading || !isValid || (!dirty && !isEditing)}
                  size="large"
                  sx={{ minWidth: 120 }}
                >
                  {isLoading
                    ? isEditing
                      ? "Updating..."
                      : "Creating..."
                    : isEditing
                      ? "Update Task"
                      : "Create Task"}
                </Button>
              </Box>
            }
          >
          <Form id="task-form">
            <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {/* Task Identifier Field */}
              <Field name="task_id">
                {({ field }: FieldProps<string>) => (
                  <Box>
                    <Typography
                      variant="subtitle2"
                      sx={{ mb: 1, fontWeight: 600 }}
                    >
                      Task Identifier
                    </Typography>
                    <TextField
                      {...field}
                      fullWidth
                      error={touched.task_id && !!errors.task_id}
                      helperText={
                        touched.task_id && errors.task_id
                          ? errors.task_id
                          : "A unique identifier for this task (e.g., task-123456)"
                      }
                      disabled={isLoading}
                      value={field.value || ""}
                      placeholder="Enter a unique task identifier"
                      sx={{
                        "& .MuiInputBase-root": {
                          fontSize: "0.95rem",
                        },
                      }}
                    />
                  </Box>
                )}
              </Field>


              {/* Prompt Field */}
              <Field name="prompt">
                {({ field }: FieldProps<string>) => {
                  const analysis = analyzePrompt(field.value || "");
                  return (
                    <Box>
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          gap: 1,
                          mb: 1,
                        }}
                      >
                        <Typography
                          variant="subtitle2"
                          sx={{ fontWeight: 600 }}
                        >
                          Task Prompt
                        </Typography>
                        <Chip
                          label={getCharacterCountText(analysis.characterCount)}
                          size="small"
                          variant="outlined"
                          sx={{ fontSize: "0.65rem", height: 20 }}
                        />
                        <Chip
                          label={analysis.label}
                          size="small"
                          color={analysis.color}
                          sx={{ fontSize: "0.65rem", height: 20 }}
                        />
                      </Box>
                      <TextField
                        {...field}
                        fullWidth
                        multiline
                        rows={8}
                        placeholder="Describe the task that the AI agent should perform...

Examples:
• Navigate to the homepage and find the search functionality
• Add a product to the shopping cart and proceed to checkout
• Fill out the contact form with valid information"
                        error={touched.prompt && !!errors.prompt}
                        helperText={
                          touched.prompt && errors.prompt
                            ? errors.prompt
                            : "Be specific and detailed about what the agent should accomplish"
                        }
                        disabled={isLoading}
                        value={field.value || ""}
                        sx={{
                          "& .MuiInputBase-root": {
                            fontFamily:
                              "ui-monospace, 'Cascadia Code', 'Source Code Pro', Consolas, 'Liberation Mono', monospace",
                            fontSize: "0.9rem",
                            lineHeight: 1.6,
                          },
                          "& .MuiFormHelperText-root": {
                            fontSize: "0.75rem",
                          },
                        }}
                      />
                    </Box>
                  );
                }}
              </Field>

              {/* Task Config Field (Combined) - Only show when gym verification strategy is grader_config */}
              {showGraderConfig && (
                <Box>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      mb: 1,
                    }}
                  >
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        Task Config
                      </Typography>
                      <Chip
                        label="Required"
                        size="small"
                        color="error"
                        sx={{ fontSize: "0.65rem", height: 20 }}
                      />
                    </Box>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      {/* Error icon in header that triggers popover */}
                      {touched.task_config && errors.task_config && (
                        <IconButton
                          size="small"
                          onClick={(e: React.MouseEvent<HTMLButtonElement>) => setErrorPopoverAnchor(e.currentTarget)}
                          sx={{
                            color: "error.main",
                            "&:hover": { backgroundColor: "error.light", opacity: 0.1 },
                          }}
                        >
                          <ErrorOutlineIcon fontSize="small" />
                        </IconButton>
                      )}
                      <IconButton
                        size="small"
                        onClick={() => setTaskConfigExpanded(!taskConfigExpanded)}
                      >
                        {taskConfigExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                      </IconButton>
                    </Box>
                  </Box>
                  
                  {/* Error popover - positioned to the right of the header, only show when there are errors */}
                  {touched.task_config && errors.task_config && (
                    <Popover
                      open={Boolean(errorPopoverAnchor) && Boolean(errors.task_config)}
                      anchorEl={errorPopoverAnchor}
                      onClose={() => setErrorPopoverAnchor(null)}
                      anchorOrigin={{
                        vertical: "bottom",
                        horizontal: "right",
                      }}
                      transformOrigin={{
                        vertical: "top",
                        horizontal: "right",
                      }}
                      sx={{
                        "& .MuiPopover-paper": {
                          maxWidth: 400,
                          border: "2px solid",
                          borderColor: "error.main",
                        },
                      }}
                    >
                      <Paper sx={{ p: 2, bgcolor: "background.paper", maxWidth: 400, boxShadow: 3 }}>
                        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1, mb: 1 }}>
                          <ErrorOutlineIcon sx={{ color: "error.main", mt: 0.5 }} />
                          <Typography variant="subtitle2" sx={{ fontWeight: 600, color: "error.main" }}>
                            Validation Error
                          </Typography>
                        </Box>
                        <Typography
                          variant="body2"
                          component="pre"
                          sx={{
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            fontFamily: "monospace",
                            fontSize: "0.875rem",
                            m: 0,
                            color: "text.primary",
                            lineHeight: 1.6,
                          }}
                        >
                          {errors.task_config}
                        </Typography>
                      </Paper>
                    </Popover>
                  )}
                  
                  <Collapse in={taskConfigExpanded}>
                    <Field name="task_config">
                      {({ field, form }: FieldProps<string>) => (
                        <Box>
                          <Box
                            sx={{
                              border: `2px solid ${
                                touched.task_config && errors.task_config
                                  ? "error.main"
                                  : touched.task_config
                                  ? "success.main"
                                  : "divider"
                              }`,
                              borderRadius: 1,
                              overflow: "hidden",
                              mb: 0.5,
                            }}
                          >
                              <Editor
                                height="500px"
                                defaultLanguage="json"
                                value={field.value || ""}
                                onChange={(value: string | undefined) => {
                                  form.setFieldValue("task_config", value || "");
                                  form.setFieldTouched("task_config", true);
                                  
                                  // Clear existing timeout
                                  if (validationTimeoutRef.current) {
                                    clearTimeout(validationTimeoutRef.current);
                                  }
                                  
                                  // Debounce validation to avoid validating incomplete JSON while typing
                                  // Wait 300ms after user stops typing before validating (reduced for faster feedback)
                                  validationTimeoutRef.current = setTimeout(() => {
                                    form.validateField("task_config");
                                  }, 300);
                                }}
                                options={{
                                  minimap: { enabled: false },
                                  fontSize: 13,
                                  lineNumbers: "on",
                                  folding: true,
                                  wordWrap: "on",
                                  scrollBeyondLastLine: false,
                                  automaticLayout: true,
                                  formatOnPaste: true,
                                  formatOnType: true,
                                  tabSize: 2,
                                }}
                                theme="vs-dark"
                              />
                          </Box>
                          {!errors.task_config && touched.task_config && (
                            <Typography variant="caption" color="success.main" sx={{ mt: 0.5, display: "block" }}>
                              ✓ Valid JSON format
                            </Typography>
                          )}
                          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                            <strong>Format:</strong> JSON with "grader_config" and "simulator_config" keys. 
                            Grader config must match exact schema (extract_states_config, state_grader_configs, etc.). 
                            Simulator config is optional but must match schema if included.
                          </Typography>
                        </Box>
                      )}
                    </Field>
                  </Collapse>
                  {!taskConfigExpanded && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
                      {touched.task_config && errors.task_config && (
                        <>
                          <ErrorOutlineIcon 
                            sx={{ 
                              color: "error.main", 
                              fontSize: "1rem",
                              cursor: "pointer",
                            }}
                            onClick={(e: React.MouseEvent<SVGSVGElement>) => setErrorPopoverAnchor(e.currentTarget as unknown as HTMLElement)}
                          />
                          <Typography 
                            variant="caption" 
                            color="error.main" 
                            sx={{ display: "block", fontWeight: 600, flex: 1 }}
                          >
                            Validation errors - click icon to view details
                          </Typography>
                        </>
                      )}
                      {!errors.task_config && values.task_config && (
                        <Typography 
                          variant="caption" 
                          color="text.secondary" 
                          sx={{ display: "block" }}
                        >
                          Config present (expand to edit)
                        </Typography>
                      )}
                      {!values.task_config && !errors.task_config && (
                        <Typography 
                          variant="caption" 
                          color="error.main" 
                          sx={{ display: "block" }}
                        >
                          ⚠️ Required: Define verification rules for harness-side grading
                        </Typography>
                      )}
                    </Box>
                  )}
                </Box>
              )}

              {showVerifierFileUpload && (
                <Box>
                  <Typography
                    variant="subtitle2"
                    sx={{ mb: 1, fontWeight: 600 }}
                  >
                    Verifier Script (Python)
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block", mb: 2 }}
                  >
                    Upload a Python script with on_start() and on_end() functions to verify task completion.
                  </Typography>
                  <Box
                    sx={{
                      border: "2px dashed",
                      borderColor: verifierFile ? "success.main" : "divider",
                      borderRadius: 1,
                      p: 2,
                      backgroundColor: verifierFile ? "success.50" : "background.paper",
                    }}
                  >
                    <DropzoneArea
                      onChange={(files: File[]) => {if (files.length > 0) setVerifierFile(files[0]);}}
                      acceptedFiles={VERIFIER_ACCEPTED_FILES}
                      filesLimit={1}
                      dropzoneText={verifierFile ? `✓ ${verifierFile.name}` : "Drag and drop a .py file here or click to browse"}
                      showAlerts={false}
                      maxFileSize={1000000}
                    />
                  </Box>
                  {verifierFile && (
                    <Typography
                      variant="caption"
                      color="success.main"
                      sx={{ mt: 1, display: "block", fontWeight: 600 }}
                    >
                      ✓ New script uploaded: {verifierFile.name}
                    </Typography>
                  )}
                  {verifierFilePath && (
                    <Typography
                      variant="caption"
                      color={verifierFile ? "success.main" : "text.secondary"}
                      sx={{ mt: 0.5, display: "block", fontWeight: verifierFile ? 600 : 400 }}
                    >
                      {verifierFile ? "Will be stored at: " : "Current verifier: "}{verifierFilePath}
                    </Typography>
                  )}
                  {isEditing && task?.verifier_path && !verifierFile && (
                    <Typography
                      variant="caption"
                      color="info.main"
                      sx={{ mt: 0.5, display: "block" }}
                    >
                      ℹ️ Upload a new file to replace the existing verifier script
                    </Typography>
                  )}
                </Box>
              )}

              {/* Loading indicator when fetching gym data */}
              {isLoadingGym && gymId && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, color: "text.secondary" }}>
                  <CircularProgress size={16} />
                  <Typography variant="caption">Loading gym verification strategy...</Typography>
                </Box>
              )}
            </Box>
          </Form>
        </SidebarForm>
        );
      }}
    </Formik>
  );
}
