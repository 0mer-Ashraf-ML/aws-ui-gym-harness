import { TextField, Button, Box, Typography, Alert, FormControl, InputLabel, Select, MenuItem, Tooltip } from "@mui/material";
import { Formik, Form, Field } from "formik";
import * as Yup from "yup";
import HttpIcon from "@mui/icons-material/Http";
// @ts-ignore
import StorageIcon from "@mui/icons-material/Storage";
import CodeIcon from "@mui/icons-material/Code";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import type { Gym, GymCreateRequest, GymUpdateRequest, VerificationStrategy } from "../types";
import { useCreateGym, useUpdateGym } from "../hooks/useGyms";
import SidebarForm from "./SidebarForm";

interface GymFormProps {
  open: boolean;
  onClose: () => void;
  gym?: Gym | null;
  onSuccess?: (gym: Gym) => void;
  onError?: (error: Error) => void;
}

const gymSchema = Yup.object().shape({
  name: Yup.string()
    .min(2, "Name must be at least 2 characters")
    .max(100, "Name must be less than 100 characters")
    .required("Name is required"),
  description: Yup.string()
    .min(10, "Description must be at least 10 characters")
    .max(500, "Description must be less than 500 characters")
    .required("Description is required"),
  base_url: Yup.string()
    .required("Base URL is required"),
  verification_strategy: Yup.string()
    .oneOf(
      [
        "verification_endpoint",
        "local_storage_assertions",
        "grader_config",
        "verifier_api_script"
      ],
      "Invalid verification strategy"
    )
    .required("Verification strategy is required"),
});

export default function GymForm({
  open,
  onClose,
  gym,
  onSuccess,
  onError,
}: GymFormProps) {
  const createGymMutation = useCreateGym({
    onSuccess: (createdGym) => {
      onSuccess?.(createdGym);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });
  const updateGymMutation = useUpdateGym({
    onSuccess: (updatedGym) => {
      onSuccess?.(updatedGym);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });

  const isEditing = !!gym;
  const isLoading = createGymMutation.isPending || updateGymMutation.isPending;

  const initialValues = {
    name: gym?.name || "",
    description: gym?.description || "",
    base_url: gym?.base_url || "",
    verification_strategy: (gym?.verification_strategy || "grader_config") as VerificationStrategy,
  };

  const handleSubmit = (values: typeof initialValues) => {
    // Ensure verification_strategy is always set (default to grader_config if somehow missing)
    const submitValues = {
      ...values,
      verification_strategy: values.verification_strategy || "grader_config",
    };

    if (isEditing && gym) {
      const updateData: GymUpdateRequest = submitValues;
      updateGymMutation.mutate({ uuid: gym.uuid, ...updateData });
    } else {
      const createData: GymCreateRequest = submitValues;
      createGymMutation.mutate(createData);
    }
  };

  return (
    <Formik
      initialValues={initialValues}
      validationSchema={gymSchema}
      onSubmit={handleSubmit}
      enableReinitialize
    >
      {({ errors, touched, isValid, dirty }) => (
        <SidebarForm
          open={open}
          onClose={onClose}
          title={isEditing ? "Edit Gym" : "Create New Gym"}
          width={500}
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
                form="gym-form"
                variant="contained"
                disabled={isLoading || !isValid || (!dirty && !isEditing)}
                size="large"
                sx={{ minWidth: 140 }}
              >
                {isLoading
                  ? isEditing
                    ? "Updating..."
                    : "Creating..."
                  : isEditing
                    ? "Update Gym"
                    : "Create Gym"}
              </Button>
            </Box>
          }
        >
          <Form id="gym-form">
            <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {/* Error Display */}
              {(createGymMutation.error || updateGymMutation.error) && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {createGymMutation.error?.message ||
                    updateGymMutation.error?.message ||
                    "An error occurred while saving the gym"}
                </Alert>
              )}

              {/* Gym Name Field */}
              <Field name="name">
                {({ field }: { field: any }) => (
                  <Box>
                    <Typography
                      variant="subtitle2"
                      sx={{ mb: 1, fontWeight: 600 }}
                    >
                      Gym Name
                    </Typography>
                    <TextField
                      {...field}
                      fullWidth
                      placeholder="e.g., E-commerce Testing Gym, Banking Portal Gym"
                      error={touched.name && !!errors.name}
                      helperText={
                        touched.name && errors.name
                          ? errors.name
                          : "A descriptive name for this gym environment"
                      }
                      disabled={isLoading}
                      value={field.value || ""}
                      sx={{
                        "& .MuiInputBase-root": {
                          fontSize: "0.95rem",
                        },
                      }}
                    />
                  </Box>
                )}
              </Field>

              {/* Description Field */}
              <Field name="description">
                {({ field }: { field: any }) => (
                  <Box>
                    <Typography
                      variant="subtitle2"
                      sx={{ mb: 1, fontWeight: 600 }}
                    >
                      Description
                    </Typography>
                    <TextField
                      {...field}
                      fullWidth
                      multiline
                      rows={4}
                      placeholder="Describe the purpose and functionality of this gym environment...

Examples:
• A testing environment for e-commerce websites with product browsing and checkout
• Banking portal simulation for transaction testing
• Educational platform for course navigation and enrollment"
                      error={touched.description && !!errors.description}
                      helperText={
                        touched.description && errors.description
                          ? errors.description
                          : `${(field.value || "").length}/500 characters - Explain what agents will be tested on`
                      }
                      disabled={isLoading}
                      value={field.value || ""}
                      sx={{
                        "& .MuiInputBase-root": {
                          fontSize: "0.95rem",
                          lineHeight: 1.6,
                        },
                        "& .MuiFormHelperText-root": {
                          fontSize: "0.75rem",
                        },
                      }}
                    />
                  </Box>
                )}
              </Field>

              {/* Base URL Field */}
              <Field name="base_url">
                {({ field }: { field: any }) => (
                  <Box>
                    <Typography
                      variant="subtitle2"
                      sx={{ mb: 1, fontWeight: 600 }}
                    >
                      Base URL
                    </Typography>
                    <TextField
                      {...field}
                      fullWidth
                      placeholder="https://example.com"
                      error={touched.base_url && !!errors.base_url}
                      helperText={
                        touched.base_url && errors.base_url
                          ? errors.base_url
                          : "The main URL where agents will start their interactions"
                      }
                      disabled={isLoading}
                      value={field.value || ""}
                      sx={{
                        "& .MuiInputBase-root": {
                          fontFamily:
                            "ui-monospace, 'Cascadia Code', 'Source Code Pro', Consolas, 'Liberation Mono', monospace",
                          fontSize: "0.9rem",
                        },
                      }}
                    />
                  </Box>
                )}
              </Field>

              {/* Verification Strategy Field */}
              <Field name="verification_strategy">
                {({ field }: { field: any }) => (
                  <Box>
                    <Typography
                      variant="subtitle2"
                      sx={{ fontWeight: 600, mb: 1 }}
                    >
                      Verification Strategy
                    </Typography>
                    <FormControl fullWidth error={touched.verification_strategy && !!errors.verification_strategy}>
                      <InputLabel id="verification-strategy-label" shrink={!!(field.value || "grader_config")}>
                        Select verification method
                      </InputLabel>
                      <Select
                        {...field}
                        labelId="verification-strategy-label"
                        label="Select verification method"
                        disabled={isLoading}
                        value={field.value || "grader_config"}
                        renderValue={(value) => {
                          const options = {
                            verification_endpoint: "Verify Endpoint",
                            local_storage_assertions: "Local Storage Assertions",
                            grader_config: "Grader Config (Harness)",
                            verifier_api_script: "Verifier API Script",
                          };
                          return options[value as keyof typeof options] || value;
                        }}
                      >
                        <MenuItem value="verification_endpoint">
                          <Tooltip
                            title="The gym persists task state. After the task completes, the harness calls the gym's verify endpoint and the gym returns pass or fail."
                            arrow
                            placement="right"
                          >
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, width: "100%" }}>
                              <HttpIcon fontSize="small" sx={{ color: "white" }} />
                              <Box sx={{ flex: 1 }}>
                                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                  Verify Endpoint
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  Use a dedicated endpoint to verify task completion
                                </Typography>
                              </Box>
                            </Box>
                          </Tooltip>
                        </MenuItem>
                        <MenuItem value="local_storage_assertions">
                          <Tooltip
                            title="After the task completes, the harness captures a browser localStorage snapshot and sends it to the gym. The gym evaluates assertions against that snapshot and returns per-assertion pass/fail results for richer feedback."
                            arrow
                            placement="right"
                          >
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, width: "100%" }}>
                              <StorageIcon fontSize="small" sx={{ color: "white" }} />
                              <Box sx={{ flex: 1 }}>
                                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                  Local Storage Assertions
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  Verify completion using local storage data
                                </Typography>
                              </Box>
                            </Box>
                          </Tooltip>
                        </MenuItem>
                        <MenuItem value="grader_config">
                          <Tooltip
                            title="After the task completes, the harness calls window.get_states exposed by the gym to retrieve actual and expected states, then runs the assertions locally on the harness side."
                            arrow
                            placement="right"
                          >
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, width: "100%" }}>
                              <CodeIcon fontSize="small" sx={{ color: "white" }} />
                              <Box sx={{ flex: 1 }}>
                                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                  Grader Config (Harness)
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  Harness-side verification using declarative graders
                                </Typography>
                              </Box>
                            </Box>
                          </Tooltip>
                        </MenuItem>
                        <MenuItem value="verifier_api_script">
                          <Tooltip
                            title="After the task completes, the harness uploads execution data to the gym's verifier endpoint using your custom Python script. Use this when you need bespoke verification logic."
                            arrow
                            placement="right"
                          >
                            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, width: "100%" }}>
                              <UploadFileIcon fontSize="small" sx={{ color: "white" }} />
                              <Box sx={{ flex: 1 }}>
                                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                  Verifier API Script
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  Upload custom Python scripts for verification
                                </Typography>
                              </Box>
                            </Box>
                          </Tooltip>
                        </MenuItem>
                      </Select>
                      {touched.verification_strategy && errors.verification_strategy && (
                        <Typography variant="caption" color="error" sx={{ mt: 0.5, ml: 1.75 }}>
                          {errors.verification_strategy}
                        </Typography>
                      )}
                    </FormControl>
                  </Box>
                )}
              </Field>
            </Box>
          </Form>
        </SidebarForm>
      )}
    </Formik>
  );
}
