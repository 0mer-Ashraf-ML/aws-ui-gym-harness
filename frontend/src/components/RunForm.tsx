import {
  TextField,
  Button,
  Box,
  MenuItem,
  Typography,
  Alert,
} from "@mui/material";
import { Formik, Form, Field } from "formik";
import * as Yup from "yup";
import type { Execution, ModelType } from "../types";
import { useCreateRun, useUpdateRun } from "../hooks/useRuns";
import { useGyms } from "../hooks/useGyms";
import { useTasks } from "../hooks/useTasks";
import SidebarForm from "./SidebarForm";

interface RunFormProps {
  open: boolean;
  onClose: () => void;
  run?: Execution | null;
  onSuccess?: (run: Execution) => void;
  onError?: (error: Error) => void;
  isPlayground?: boolean; // If true, show playground form (URL + prompt), otherwise batch form (gym + task)
}

// Playground form schema (for /runs page)
const playgroundSchema = Yup.object().shape({
  playground_url: Yup.string()
    .url("Must be a valid URL")
    .required("URL is required"),
  prompt: Yup.string()
    .min(10, "Prompt must be at least 10 characters")
    .required("Prompt is required"),
  model: Yup.string()
    .oneOf(["openai", "anthropic", "gemini"], "Invalid model")
    .required("Model is required"),
  number_of_iterations: Yup.number()
    .min(1, "Must be at least 1 iteration")
    .max(3, "Cannot exceed 3 iterations for playground")
    .required("Number of iterations is required"),
});

// Batch form schema (for batch runs - kept for backwards compatibility)
const runSchema = Yup.object().shape({
  gym_id: Yup.string().required("Gym is required"),
  task_id: Yup.string().required("Task is required"),
  model: Yup.string()
    .oneOf(["openai", "anthropic", "gemini"], "Invalid model")
    .required("Model is required"),
  number_of_iterations: Yup.number()
    .min(1, "Must be at least 1 iteration")
    .max(100, "Cannot exceed 100 iterations")
    .required("Number of iterations is required"),
});

const models = [
  {
    value: "openai",
    label: "OpenAI Computer Use Preview",
    description: "OpenAI's Computer Use Preview for advanced computer interaction tasks",
  },
  {
    value: "anthropic",
    label: "Anthropic Claude",
    description: "Anthropic's Claude models for reasoning and analysis",
  },
  {
    value: "gemini",
    label: "Google Gemini Computer Use",
    description: "Google's Gemini 2.5 with Computer Use for browser automation",
  },
];

export default function RunForm({
  open,
  onClose,
  run,
  onSuccess,
  onError,
  isPlayground = false, // Default to batch form for backwards compatibility
}: RunFormProps) {
  const createRunMutation = useCreateRun({
    onSuccess: (createdRun) => {
      onSuccess?.(createdRun);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });
  const updateRunMutation = useUpdateRun({
    onSuccess: (updatedRun) => {
      onSuccess?.(updatedRun);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });
  const { data: gyms = [] } = useGyms();
  const { data: tasks = [] } = useTasks();

  const isEditing = !!run;
  const isLoading = createRunMutation.isPending || updateRunMutation.isPending;

  // Playground form initial values
  const playgroundInitialValues = {
    playground_url: (run as any)?.playground_url || "",
    prompt: run?.prompt || "",
    model: run?.model || ("openai" as ModelType),
    number_of_iterations: run?.number_of_iterations || 1,
  };

  // Batch form initial values
  const batchInitialValues = {
    gym_id: run?.gym_id || "",
    task_id: run?.task_id || "",
    model: run?.model || ("" as ModelType | ""),
    number_of_iterations: run?.number_of_iterations || 1,
  };

  const initialValues = isPlayground ? playgroundInitialValues : batchInitialValues;

  const handleSubmit = (values: any) => {
    if (isPlayground) {
      // Playground submission
      const submissionData = {
        execution_type: "playground" as const,
        playground_url: values.playground_url,
        prompt: values.prompt,
        model: values.model as ModelType,
        number_of_iterations: values.number_of_iterations,
        gym_id: null, // Explicitly set to null for playground executions
      };

      if (isEditing && run) {
        // Playground runs shouldn't be editable, but handle it gracefully
        // Convert null to undefined for TypeScript compatibility with ExecutionUpdateRequest
        const updateData: any = { ...submissionData };
        if (updateData.gym_id === null) {
          updateData.gym_id = undefined;
        }
        updateRunMutation.mutate({ uuid: run.uuid, ...updateData });
      } else {
        createRunMutation.mutate(submissionData as any);
      }
    } else {
      // Batch submission
      const submissionData = {
        gym_id: values.gym_id,
        task_id: values.task_id || undefined,
        model: values.model as ModelType,
        number_of_iterations: values.number_of_iterations,
      };

      if (isEditing && run) {
        updateRunMutation.mutate({ uuid: run.uuid, ...submissionData });
      } else {
        createRunMutation.mutate(submissionData);
      }
    }
  };

  return (
    <Formik
      initialValues={initialValues}
      validationSchema={isPlayground ? playgroundSchema : runSchema}
      onSubmit={handleSubmit}
      enableReinitialize
    >
      {({
        errors,
        touched,
        isValid,
        dirty,
        values,
        setFieldValue,
        resetForm,
      }) => {
        const handleClose = () => {
          // Reset form to initial values when closing
          resetForm();
          onClose();
        };

        return (
            <SidebarForm
            open={open}
            onClose={handleClose}
            title={isEditing ? (isPlayground ? "Edit Playground Run" : "Edit Run") : (isPlayground ? "Create Playground Run" : "Create & Execute Run")}
            width={520}
            disableBackdropClick={isLoading}
            actions={
              <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
                <Button
                  onClick={handleClose}
                  disabled={isLoading}
                  variant="outlined"
                  size="large"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  form="run-form"
                  variant="contained"
                  disabled={isLoading || !isValid || (!dirty && isEditing)}
                  size="large"
                  sx={{ minWidth: 120 }}
                >
                  {isLoading
                    ? isEditing
                      ? "Updating..."
                      : "Creating & Executing..."
                    : isEditing
                      ? "Update Run"
                      : "Create & Execute Run"}
                </Button>
              </Box>
            }
          >
            <Form id="run-form">
              <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {/* Info Message */}
                {!isEditing && (
                  <Alert severity="info" sx={{ mb: 2 }}>
                    <Typography variant="body2">
                      📋 <strong>Note:</strong> Creating a {isPlayground ? "playground" : ""} run will
                      automatically start its execution. You'll see it appear in
                      the runs list and begin processing immediately.
                    </Typography>
                  </Alert>
                )}

                {/* Error Display */}
                {(createRunMutation.error || updateRunMutation.error) && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {createRunMutation.error?.message ||
                      updateRunMutation.error?.message ||
                      "An error occurred while saving the run"}
                  </Alert>
                )}

                {/* Playground URL Field */}
                {isPlayground && (
                  <Field name="playground_url">
                    {({ field }: { field: any }) => (
                      <Box>
                        <Typography
                          variant="subtitle2"
                          sx={{ mb: 1, fontWeight: 600 }}
                        >
                          URL
                        </Typography>
                        <TextField
                          fullWidth
                          name={field.name}
                          value={field.value || ""}
                          onChange={field.onChange}
                          onBlur={field.onBlur}
                          error={(touched as any).playground_url && !!(errors as any).playground_url}
                          helperText={
                            (touched as any).playground_url && (errors as any).playground_url
                              ? (errors as any).playground_url
                              : "Enter the URL where the prompt should be executed"
                          }
                          disabled={isLoading}
                          placeholder="https://example.com"
                          sx={{
                            "& .MuiInputBase-root": {
                              fontSize: "0.95rem",
                            },
                          }}
                        />
                      </Box>
                    )}
                  </Field>
                )}

                {/* Prompt Field (for playground) */}
                {isPlayground && (
                  <Field name="prompt">
                    {({ field }: { field: any }) => (
                      <Box>
                        <Typography
                          variant="subtitle2"
                          sx={{ mb: 1, fontWeight: 600 }}
                        >
                          Prompt
                        </Typography>
                        <TextField
                          fullWidth
                          multiline
                          rows={4}
                          name={field.name}
                          value={field.value || ""}
                          onChange={field.onChange}
                          onBlur={field.onBlur}
                          error={(touched as any).prompt && !!(errors as any).prompt}
                          helperText={
                            (touched as any).prompt && (errors as any).prompt
                              ? (errors as any).prompt
                              : "Enter the task prompt to execute"
                          }
                          disabled={isLoading}
                          placeholder="Describe what you want the AI to do..."
                          sx={{
                            "& .MuiInputBase-root": {
                              fontSize: "0.95rem",
                            },
                          }}
                        />
                      </Box>
                    )}
                  </Field>
                )}

                {/* Gym Selection Field (for batch) */}
                {!isPlayground && (
                  <Field name="gym_id">
                  {({ field }: { field: any }) => (
                    <Box>
                      <Typography
                        variant="subtitle2"
                        sx={{ mb: 1, fontWeight: 600 }}
                      >
                        Target Gym
                      </Typography>
                      <TextField
                        select
                        fullWidth
                        name={field.name}
                        value={field.value || ""}
                        onChange={(event) => {
                          setFieldValue("gym_id", event.target.value);
                          // Reset task selection when gym changes
                          setFieldValue("task_id", "");
                        }}
                        onBlur={field.onBlur}
                        error={(touched as any).gym_id && !!(errors as any).gym_id}
                        helperText={
                          (touched as any).gym_id && (errors as any).gym_id
                            ? (errors as any).gym_id
                            : "Select the gym environment where the run will execute"
                        }
                        disabled={isLoading}
                        sx={{
                          "& .MuiInputBase-root": {
                            fontSize: "0.95rem",
                          },
                        }}
                      >
                        <MenuItem value="">
                          <em>Select a gym...</em>
                        </MenuItem>
                        {gyms.map((gym) => (
                          <MenuItem key={gym.uuid} value={gym.uuid}>
                            <Box>
                              <Typography
                                variant="body1"
                                sx={{ fontWeight: 500 }}
                              >
                                {gym.name}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{ display: "block", mt: 0.5 }}
                              >
                                {gym.description?.length > 60
                                  ? `${gym.description.slice(0, 60)}...`
                                  : gym.description}
                              </Typography>
                            </Box>
                          </MenuItem>
                        ))}
                      </TextField>
                    </Box>
                  )}
                </Field>
                )}

                {/* Task Selection Field (for batch) */}
                {!isPlayground && (
                  <Field name="task_id">
                  {({ field }: { field: any }) => (
                    <Box>
                      <Typography
                        variant="subtitle2"
                        sx={{ mb: 1, fontWeight: 600 }}
                      >
                        Task
                      </Typography>
                      <TextField
                        select
                        fullWidth
                        name={field.name}
                        value={field.value || ""}
                        onChange={(event) => {
                          setFieldValue("task_id", event.target.value);
                        }}
                        onBlur={field.onBlur}
                        error={(touched as any).task_id && !!(errors as any).task_id}
                        helperText={
                          (touched as any).task_id && (errors as any).task_id
                            ? (errors as any).task_id
                            : "Select a task from the selected gym"
                        }
                        disabled={isLoading}
                        sx={{
                          "& .MuiInputBase-root": {
                            fontSize: "0.95rem",
                          },
                        }}
                      >
                        <MenuItem value="">
                          <em>Select a task...</em>
                        </MenuItem>

                        {tasks
                          .filter((task) =>
                            (values as any).gym_id
                              ? task.gym_id === (values as any).gym_id
                              : true,
                          )
                          .map((task) => (
                            <MenuItem key={task.uuid} value={task.uuid}>
                              <Box>
                                <Typography
                                  variant="body1"
                                  sx={{ fontWeight: 500 }}
                                >
                                  Task #{task.task_id}
                                </Typography>
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                  sx={{ display: "block", mt: 0.5 }}
                                >
                                  {task.prompt?.length > 80
                                    ? `${task.prompt.slice(0, 80)}...`
                                    : task.prompt}
                                </Typography>
                              </Box>
                            </MenuItem>
                          ))}
                      </TextField>
                    </Box>
                  )}
                </Field>
                )}

                {/* Model Selection Field */}
                <Field name="model">
                  {({ field }: { field: any }) => (
                    <Box>
                      <Typography
                        variant="subtitle2"
                        sx={{ mb: 1, fontWeight: 600 }}
                      >
                        AI Model
                      </Typography>
                      <TextField
                        select
                        fullWidth
                        name={field.name}
                        value={field.value || ""}
                        onChange={(event) => {
                          setFieldValue("model", event.target.value);
                        }}
                        onBlur={field.onBlur}
                        error={touched.model && !!errors.model}
                        helperText={
                          touched.model && errors.model
                            ? errors.model
                            : isPlayground
                            ? "Select the AI model to execute the prompt"
                            : "Select the AI model to execute the task"
                        }
                        disabled={isLoading}
                        sx={{
                          "& .MuiInputBase-root": {
                            fontSize: "0.95rem",
                          },
                        }}
                      >
                        <MenuItem value="">
                          <em>Select a model...</em>
                        </MenuItem>
                        {models.map((model) => (
                          <MenuItem key={model.value} value={model.value} disabled={model.value === "unified"}>
                            <Box>
                              <Typography
                                variant="body1"
                                sx={{ fontWeight: 500 }}
                              >
                                {model.label}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{ display: "block", mt: 0.5 }}
                              >
                                {model.description}
                              </Typography>
                            </Box>
                          </MenuItem>
                        ))}
                      </TextField>
                    </Box>
                  )}
                </Field>

                {/* Number of Iterations Field */}
                <Field name="number_of_iterations">
                  {({ field }: { field: any }) => (
                    <Box>
                      <Typography
                        variant="subtitle2"
                        sx={{ mb: 1, fontWeight: 600 }}
                      >
                        Number of Iterations
                      </Typography>
                      <TextField
                        {...field}
                        type="number"
                        fullWidth
                        inputProps={{ min: 1, max: isPlayground ? 3 : 100, step: 1 }}
                        error={
                          touched.number_of_iterations &&
                          !!errors.number_of_iterations
                        }
                        helperText={
                          touched.number_of_iterations &&
                          errors.number_of_iterations
                            ? errors.number_of_iterations
                            : isPlayground
                            ? "How many times to run this prompt (1-3)"
                            : "How many times to run this task (1-100)"
                        }
                        disabled={isLoading}
                        value={field.value || 1}
                        sx={{
                          "& .MuiInputBase-root": {
                            fontSize: "0.95rem",
                          },
                        }}
                      />
                    </Box>
                  )}
                </Field>
              </Box>
            </Form>
          </SidebarForm>
        );
      }}
    </Formik>
  );
}
