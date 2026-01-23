import { useState } from "react";
import {
  Typography,
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  MenuItem,
  Alert,
  Stepper,
  Step,
  StepLabel,
  CircularProgress,
  Chip,
  Divider,
} from "@mui/material";
import {
  PlayArrow as RunIcon,
  FitnessCenter as GymIcon,
  Assignment as TaskIcon,
  SmartToy as ModelIcon,
} from "@mui/icons-material";
import { Formik, Form, Field } from "formik";
import * as Yup from "yup";
import { useGyms } from "../hooks/useGyms";
import { useTasks } from "../hooks/useTasks";
import { useCreateRun } from "../hooks/useRuns";
import type { ModelType } from "../types";
import SimplePageHeader from "../components/SimplePageHeader";

const runSchema = Yup.object().shape({
  gym_id: Yup.string().required("Gym is required"),
  task_id: Yup.string().required("Task is required"),
  model: Yup.string()
    .oneOf(["openai", "anthropic"], "Invalid model")
    .required("Model is required"),
  iterations: Yup.number()
    .min(1, "Must be at least 1 iteration")
    .max(100, "Cannot exceed 100 iterations")
    .required("Number of iterations is required"),
});

const models: { value: ModelType; label: string; description: string }[] = [
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
];

export default function Run() {
  const [runCreated, setRunCreated] = useState(false);
  const [createdRunId, setCreatedRunId] = useState<string | null>(null);
  
  const { data: gyms, isLoading: gymsLoading } = useGyms();
  const { data: tasks, isLoading: tasksLoading } = useTasks();
  const createRunMutation = useCreateRun();

  const initialValues = {
    gym_id: "",
    task_id: "",
    model: "" as ModelType | "",
    iterations: 1,
  };

  const handleSubmit = (values: typeof initialValues) => {
    createRunMutation.mutate(
      {
        gym_id: values.gym_id,
        task_id: values.task_id,
        model: values.model as ModelType,
        number_of_iterations: values.iterations,
      },
      {
        onSuccess: (data) => {
          setCreatedRunId(data.uuid);
          setRunCreated(true);
        },
      },
    );
  };

  const steps = [
    "Select Gym",
    "Select Task",
    "Configure Model",
    "Review & Run",
  ];

  if (runCreated && createdRunId) {
    return (
      <Box>
        <Typography variant="h4" gutterBottom>
          Run Created Successfully
        </Typography>
        <Alert severity="success" sx={{ mb: 3 }}>
          Your run has been created and queued for execution.
        </Alert>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Run Details
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <Typography variant="body1">Run ID:</Typography>
              <Chip label={createdRunId} variant="outlined" />
            </Box>
            <Button
              variant="contained"
              onClick={() => {
                setRunCreated(false);
                setCreatedRunId(null);
              }}
            >
              Create Another Run
            </Button>
          </CardContent>
        </Card>
      </Box>
    );
  }

  return (
    <Box>
      <SimplePageHeader
        icon={<RunIcon sx={{ fontSize: 48 }} />}
        title="Create New Run"
        description="Configure and execute a new run by selecting a gym environment, task, and model configuration."
      />

      <Stepper sx={{ mb: 4 }}>
        {steps.map((label) => (
          <Step key={label} active>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Card>
        <CardContent>
          <Formik
            initialValues={initialValues}
            validationSchema={runSchema}
            onSubmit={handleSubmit}
          >
            {({ errors, touched }) => (
              <Form>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {/* Gym Selection */}
                  <Box>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        mb: 2,
                      }}
                    >
                      <GymIcon color="primary" />
                      <Typography variant="h6">
                        Select Gym Environment
                      </Typography>
                    </Box>
                    <Field name="gym_id">
                      {({ field, form }: any) => (
                        <TextField
                          select
                          fullWidth
                          label="Gym"
                          placeholder="Choose a gym environment"
                          name={field.name}
                          value={field.value || ""}
                          onChange={(event) => {
                            form.setFieldValue("gym_id", event.target.value);
                          }}
                          onBlur={field.onBlur}
                          error={touched.gym_id && !!errors.gym_id}
                          helperText={touched.gym_id && errors.gym_id}
                          disabled={gymsLoading || createRunMutation.isPending}
                        >
                          {gymsLoading ? (
                            <MenuItem disabled>
                              <CircularProgress size={20} sx={{ mr: 1 }} />
                              Loading gyms...
                            </MenuItem>
                          ) : (
                            [
                              <MenuItem key="empty" value="">
                                <em>Select a gym...</em>
                              </MenuItem>,
                              ...(gyms || []).map((gym) => (
                                <MenuItem key={gym.uuid} value={gym.uuid}>
                                  <Box>
                                    <Typography variant="body1">
                                      {gym.name}
                                    </Typography>
                                    <Typography
                                      variant="caption"
                                      color="text.secondary"
                                    >
                                      {gym.description}
                                    </Typography>
                                  </Box>
                                </MenuItem>
                              )),
                            ]
                          )}
                        </TextField>
                      )}
                    </Field>
                  </Box>

                  <Divider />

                  {/* Task Selection */}
                  <Box>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        mb: 2,
                      }}
                    >
                      <TaskIcon color="primary" />
                      <Typography variant="h6">Select Task</Typography>
                    </Box>
                    <Field name="task_id">
                      {({ field, form }: any) => (
                        <TextField
                          select
                          fullWidth
                          label="Task"
                          placeholder="Choose a task for the agent"
                          name={field.name}
                          value={field.value || ""}
                          onChange={(event) => {
                            form.setFieldValue("task_id", event.target.value);
                          }}
                          onBlur={field.onBlur}
                          error={touched.task_id && !!errors.task_id}
                          helperText={touched.task_id && errors.task_id}
                          disabled={tasksLoading || createRunMutation.isPending}
                        >
                          {tasksLoading ? (
                            <MenuItem disabled>
                              <CircularProgress size={20} sx={{ mr: 1 }} />
                              Loading tasks...
                            </MenuItem>
                          ) : (
                            [
                              <MenuItem key="empty" value="">
                                <em>Select a task...</em>
                              </MenuItem>,
                              ...(tasks || []).map((task) => (
                                <MenuItem key={task.uuid} value={task.uuid}>
                                  <Box>
                                    <Typography variant="body1">
                                      Task #{task.task_id}
                                    </Typography>
                                    <Typography
                                      variant="caption"
                                      color="text.secondary"
                                      sx={{
                                        display: "block",
                                        maxWidth: 400,
                                        overflow: "hidden",
                                        textOverflow: "ellipsis",
                                        whiteSpace: "nowrap",
                                      }}
                                    >
                                      {task.prompt}
                                    </Typography>
                                  </Box>
                                </MenuItem>
                              )),
                            ]
                          )}
                        </TextField>
                      )}
                    </Field>
                  </Box>

                  <Divider />

                  {/* Model Selection */}
                  <Box>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        mb: 2,
                      }}
                    >
                      <ModelIcon color="primary" />
                      <Typography variant="h6">Select Model</Typography>
                    </Box>
                    <Field name="model">
                      {({ field, form }: any) => (
                        <TextField
                          select
                          fullWidth
                          label="Model Provider"
                          placeholder="Choose AI model provider"
                          name={field.name}
                          value={field.value || ""}
                          onChange={(event) => {
                            form.setFieldValue("model", event.target.value);
                          }}
                          onBlur={field.onBlur}
                          error={touched.model && !!errors.model}
                          helperText={touched.model && errors.model}
                          disabled={createRunMutation.isPending}
                        >
                          {[
                            <MenuItem key="empty" value="">
                              <em>Select a model...</em>
                            </MenuItem>,
                            ...models.map((model) => (
                              <MenuItem key={model.value} value={model.value}>
                                <Box>
                                  <Typography variant="body1">
                                    {model.label}
                                  </Typography>
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                  >
                                    {model.description}
                                  </Typography>
                                </Box>
                              </MenuItem>
                            )),
                          ]}
                        </TextField>
                      )}
                    </Field>
                  </Box>

                  <Divider />

                  {/* Iterations */}
                  <Box>
                    <Typography variant="h6" gutterBottom>
                      Number of Iterations
                    </Typography>
                    <Field name="iterations">
                      {({ field }: any) => (
                        <TextField
                          {...field}
                          type="number"
                          fullWidth
                          label="Iterations"
                          inputProps={{ min: 1, max: 100 }}
                          error={touched.iterations && !!errors.iterations}
                          helperText={
                            touched.iterations && errors.iterations
                              ? errors.iterations
                              : "Number of times to run the task (1-100)"
                          }
                          disabled={createRunMutation.isPending}
                          sx={{ maxWidth: 200 }}
                          value={field.value || 1}
                        />
                      )}
                    </Field>
                  </Box>

                  <Divider />

                  {/* Submit */}
                  <Box
                    sx={{ display: "flex", justifyContent: "flex-end", gap: 2 }}
                  >
                    <Button
                      type="submit"
                      variant="contained"
                      size="large"
                      startIcon={
                        createRunMutation.isPending ? (
                          <CircularProgress size={20} />
                        ) : (
                          <RunIcon />
                        )
                      }
                      disabled={createRunMutation.isPending}
                    >
                      {createRunMutation.isPending
                        ? "Creating Run..."
                        : "Create & Execute Run"}
                    </Button>
                  </Box>
                </Box>
              </Form>
            )}
          </Formik>
        </CardContent>
      </Card>

      {createRunMutation.error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          Failed to create run. Please try again.
        </Alert>
      )}
    </Box>
  );
}
