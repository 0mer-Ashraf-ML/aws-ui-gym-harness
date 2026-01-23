import {
  TextField,
  Button,
  Box,
  MenuItem,
  Typography,
  FormControl,
  FormLabel,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Tooltip,
  InputAdornment,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SearchIcon from "@mui/icons-material/Search";
import { Formik, Form, Field } from "formik";
import * as Yup from "yup";
import { useState, useEffect, useMemo } from "react";
import type { Batch, ModelType, Task } from "../types";
import { useCreateBatch, useUpdateBatch } from "../hooks/useBatches";
import { useGyms } from "../hooks/useGyms";
import { useTasksByGym } from "../hooks/useTasks";
import SidebarForm from "./SidebarForm";

interface BatchFormProps {
  open: boolean;
  onClose: () => void;
  batch?: Batch | null;
  onSuccess?: (batch: Batch) => void;
  onError?: (error: Error) => void;
}

const batchSchema = Yup.object().shape({
  name: Yup.string().required("Batch name is required"),
  gym_id: Yup.string().required("Gym is required"),
  number_of_iterations: Yup.number()
    .min(1, "Must be at least 1 iteration")
    .max(10, "Cannot exceed 10 iterations")
    .required("Number of iterations is required"),
  selected_models: Yup.array()
    .of(Yup.string())
    .min(1, "At least one model must be selected")
    .required("Model selection is required"),
  selected_task_ids: Yup.array()
    .of(Yup.string())
    .min(1, "At least one task must be selected")
    .required("Task selection is required"),
});

export default function BatchForm({
  open,
  onClose,
  batch,
  onSuccess,
  onError,
}: BatchFormProps) {
  const createBatchMutation = useCreateBatch({
    onSuccess: (createdBatch) => {
      onSuccess?.(createdBatch);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });
  const updateBatchMutation = useUpdateBatch({
    onSuccess: (updatedBatch) => {
      onSuccess?.(updatedBatch);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });
  const { data: gyms = [] } = useGyms();
  const [taskSelectionExpanded, setTaskSelectionExpanded] = useState(true); // Start expanded to show requirement
  const [formGymId, setFormGymId] = useState<string>(batch?.gym_id || "");
  const [taskSearchTerm, setTaskSearchTerm] = useState<string>("");
  
  // Update formGymId when batch changes
  useEffect(() => {
    if (batch?.gym_id) {
      setFormGymId(batch.gym_id);
    }
  }, [batch?.gym_id]);
  
  // Fetch tasks when gym is selected
  const { data: tasks = [], isLoading: tasksLoading } = useTasksByGym(formGymId);
  
  // Filter tasks based on search term
  const filteredTasks = useMemo(() => {
    if (!taskSearchTerm.trim()) return tasks;
    const searchLower = taskSearchTerm.toLowerCase().trim();
    return tasks.filter((task) => 
      task.task_id.toLowerCase().includes(searchLower) ||
      task.prompt.toLowerCase().includes(searchLower)
    );
  }, [tasks, taskSearchTerm]);
  
  // Track previous gym ID to detect changes
  const [prevGymId, setPrevGymId] = useState<string>("");

  const isEditing = !!batch;
  const isLoading = createBatchMutation.isPending || updateBatchMutation.isPending;

  const initialValues = {
    name: batch?.name || "",
    gym_id: batch?.gym_id || "",
    number_of_iterations: batch?.number_of_iterations || 1,
    selected_models: ["openai"] as ModelType[], // Default to OpenAI only
    selected_task_ids: [] as string[], // Must select at least one task
  };

  const handleSubmit = (values: typeof initialValues) => {
    const submissionData: any = {
      name: values.name,
      gym_id: values.gym_id,
      number_of_iterations: values.number_of_iterations,
      selected_models: values.selected_models,
      selected_task_ids: values.selected_task_ids, // Always include - required field
    };

    if (isEditing && batch) {
      updateBatchMutation.mutate({
        uuid: batch.uuid,
        ...submissionData,
      });
    } else {
      createBatchMutation.mutate(submissionData);
    }
  };

  return (
    <SidebarForm
      open={open}
      onClose={onClose}
      title={isEditing ? "Edit Batch" : "Create Batch"}
      width={400}
    >
      <Formik
        initialValues={initialValues}
        validationSchema={batchSchema}
        onSubmit={(values) => handleSubmit(values)}
        enableReinitialize
      >
        {({ values, errors, touched, setFieldValue }) => {
          // Update formGymId when gym selection changes to trigger task fetching
          if (values.gym_id && values.gym_id !== formGymId && values.gym_id !== prevGymId) {
            setFormGymId(values.gym_id);
            setPrevGymId(values.gym_id);
            // Reset task selection and search when gym changes
            setFieldValue("selected_task_ids", []);
            setTaskSearchTerm("");
            setTaskSelectionExpanded(true); // Auto-expand to show task selection requirement
          }

          // Handle task checkbox changes
          const handleTaskToggle = (taskUuid: string) => {
            const currentIds = values.selected_task_ids || [];
            const newIds = currentIds.includes(taskUuid)
              ? currentIds.filter((id) => id !== taskUuid)
              : [...currentIds, taskUuid];
            setFieldValue("selected_task_ids", newIds);
          };

          // Handle Select All / Deselect All (operates on filtered tasks only)
          const handleSelectAllTasks = () => {
            if (filteredTasks.length === 0) return;
            const currentIds = values.selected_task_ids || [];
            const filteredIds = filteredTasks.map((task) => task.uuid);
            // Add filtered task IDs to selection (union)
            const newIds = [...new Set([...currentIds, ...filteredIds])];
            setFieldValue("selected_task_ids", newIds);
          };

          const handleDeselectAllTasks = () => {
            if (filteredTasks.length === 0) return;
            const currentIds = values.selected_task_ids || [];
            const filteredIds = new Set(filteredTasks.map((task) => task.uuid));
            // Remove filtered task IDs from selection
            const newIds = currentIds.filter((id) => !filteredIds.has(id));
            setFieldValue("selected_task_ids", newIds);
          };

          const allFilteredTasksSelected =
            filteredTasks.length > 0 &&
            filteredTasks.every((task) => values.selected_task_ids?.includes(task.uuid));

          const someFilteredTasksSelected =
            filteredTasks.length > 0 &&
            filteredTasks.some((task) => values.selected_task_ids?.includes(task.uuid)) &&
            !allFilteredTasksSelected;

          return (
          <Form>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <Field
                as={TextField}
                name="name"
                label="Batch Name"
                fullWidth
                error={touched.name && !!errors.name}
                helperText={touched.name && errors.name}
                required
              />

              <Field
                as={TextField}
                name="gym_id"
                label="Gym"
                select
                fullWidth
                error={touched.gym_id && !!errors.gym_id}
                helperText={touched.gym_id && errors.gym_id}
                required
              >
                {gyms.map((gym) => (
                  <MenuItem key={gym.uuid} value={gym.uuid}>
                    {gym.name}
                  </MenuItem>
                ))}
              </Field>

              {/* Task Selection Section - Required */}
              {values.gym_id && (
                <Accordion
                  expanded={taskSelectionExpanded}
                  onChange={(_, isExpanded) => setTaskSelectionExpanded(isExpanded)}
                  sx={{ mt: 1 }}
                >
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Box sx={{ display: "flex", alignItems: "center", width: "100%" }}>
                      <Typography variant="body1" sx={{ flexGrow: 1 }}>
                        Select Tasks <Typography component="span" color="error">*</Typography>
                      </Typography>
                      {values.selected_task_ids && values.selected_task_ids.length > 0 ? (
                        <Typography variant="caption" color="text.secondary" sx={{ mr: 2 }}>
                          {values.selected_task_ids.length} of {tasks.length} selected
                          {taskSearchTerm && ` (${filteredTasks.length} shown)`}
                        </Typography>
                      ) : (
                        <Typography variant="caption" color="error" sx={{ mr: 2 }}>
                          No tasks selected
                        </Typography>
                      )}
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      {tasksLoading ? (
                        <Typography variant="body2" color="text.secondary">
                          Loading tasks...
                        </Typography>
                      ) : tasks.length === 0 ? (
                        <Typography variant="body2" color="text.secondary">
                          No tasks found in this gym.
                        </Typography>
                      ) : (
                        <>
                          {/* Task Search Input */}
                          <TextField
                            size="small"
                            placeholder="Search tasks by ID or prompt..."
                            value={taskSearchTerm}
                            onChange={(e) => setTaskSearchTerm(e.target.value)}
                            InputProps={{
                              startAdornment: (
                                <InputAdornment position="start">
                                  <SearchIcon fontSize="small" />
                                </InputAdornment>
                              ),
                            }}
                            sx={{ mb: 1 }}
                          />
                          
                          <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={handleSelectAllTasks}
                              disabled={allFilteredTasksSelected || filteredTasks.length === 0}
                            >
                              Select All {taskSearchTerm ? "Filtered" : ""}
                            </Button>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={handleDeselectAllTasks}
                              disabled={!someFilteredTasksSelected && !allFilteredTasksSelected}
                            >
                              Deselect All {taskSearchTerm ? "Filtered" : ""}
                            </Button>
                          </Box>
                          
                          {filteredTasks.length === 0 ? (
                            <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>
                              No tasks match your search "{taskSearchTerm}"
                            </Typography>
                          ) : (
                            <FormControl 
                              component="fieldset"
                              error={touched.selected_task_ids && !!errors.selected_task_ids}
                              required
                            >
                              <FormLabel component="legend">
                                Select at least one task to run
                                {taskSearchTerm && ` (showing ${filteredTasks.length} of ${tasks.length})`}
                              </FormLabel>
                              <FormGroup>
                                {filteredTasks.map((task: Task) => (
                                <Tooltip
                                  key={task.uuid}
                                  title={task.prompt}
                                  placement="right"
                                  arrow
                                >
                                  <FormControlLabel
                                    control={
                                      <Checkbox
                                        checked={
                                          values.selected_task_ids?.includes(task.uuid) ||
                                          false
                                        }
                                        onChange={() => handleTaskToggle(task.uuid)}
                                      />
                                    }
                                    label={
                                      <Typography
                                        variant="body2"
                                        sx={{
                                          overflow: "hidden",
                                          textOverflow: "ellipsis",
                                          whiteSpace: "nowrap",
                                          maxWidth: 300,
                                        }}
                                      >
                                        {task.task_id}
                                      </Typography>
                                    }
                                  />
                                </Tooltip>
                              ))}
                            </FormGroup>
                            {touched.selected_task_ids && errors.selected_task_ids && (
                              <Typography variant="caption" color="error" sx={{ mt: 1 }}>
                                {errors.selected_task_ids}
                              </Typography>
                            )}
                          </FormControl>
                          )}
                        </>
                      )}
                    </Box>
                  </AccordionDetails>
                </Accordion>
              )}

              <Field
                as={TextField}
                name="number_of_iterations"
                label="Number of Iterations"
                type="number"
                fullWidth
                inputProps={{ min: 1, max: 10 }}
                error={touched.number_of_iterations && !!errors.number_of_iterations}
                helperText={touched.number_of_iterations && errors.number_of_iterations}
                required
              />

              <FormControl 
                component="fieldset" 
                error={touched.selected_models && !!errors.selected_models}
                required
              >
                <FormLabel component="legend">Select Models</FormLabel>
                <FormGroup>
                  {[
                    { value: "openai", label: "OpenAI" },
                    { value: "anthropic", label: "Anthropic" },
                    { value: "gemini", label: "Gemini" },
                  ].map((model) => (
                    <FormControlLabel
                      key={model.value}
                      control={
                        <Field
                          as={Checkbox}
                          name="selected_models"
                          value={model.value}
                          checked={values.selected_models.includes(model.value as ModelType)}
                        />
                      }
                      label={model.label}
                    />
                  ))}
                </FormGroup>
                {touched.selected_models && errors.selected_models && (
                  <Typography variant="caption" color="error" sx={{ mt: 1 }}>
                    {errors.selected_models}
                  </Typography>
                )}
              </FormControl>

              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {values.selected_task_ids && values.selected_task_ids.length > 0
                  ? `This batch will run ${values.selected_task_ids.length} selected task${values.selected_task_ids.length !== 1 ? 's' : ''} from the selected gym for the selected models, with ${values.number_of_iterations} iteration${values.number_of_iterations !== 1 ? 's' : ''} each.`
                  : `Please select at least one task to create the batch.`}
              </Typography>

              <Box sx={{ display: "flex", gap: 2, mt: 3 }}>
                <Button
                  type="button"
                  variant="outlined"
                  onClick={onClose}
                  disabled={isLoading}
                  fullWidth
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="contained"
                  color={Object.keys(errors).length > 0 ? "error" : "primary"}
                  disabled={
                    isLoading || 
                    Object.keys(errors).length > 0 ||
                    !values.selected_task_ids ||
                    values.selected_task_ids.length === 0
                  }
                  fullWidth
                >
                  {isLoading
                    ? isEditing
                      ? "Updating..."
                      : "Creating..."
                    : isEditing
                    ? "Update Batch"
                    : "Create Batch"}
                </Button>
              </Box>
            </Box>
          </Form>
          );
        }}
      </Formik>
    </SidebarForm>
  );
}
