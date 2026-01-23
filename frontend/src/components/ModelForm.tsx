import {
  TextField,
  Button,
  Box,
  MenuItem,
  Typography,
  InputAdornment,
  IconButton,
} from "@mui/material";
import { Visibility, VisibilityOff } from "@mui/icons-material";
import { Formik, Form, Field } from "formik";
import * as Yup from "yup";
import { useState } from "react";
import type { Model, ModelType } from "../types";
import { useCreateModel, useUpdateModel } from "../hooks/useModels";
import SidebarForm from "./SidebarForm";

interface ModelFormProps {
  open: boolean;
  onClose: () => void;
  model?: Model | null;
  onSuccess?: (model: Model) => void;
  onError?: (error: Error) => void;
}

const modelTypes: { value: ModelType; label: string; description: string }[] = [
  {
    value: "openai",
    label: "OpenAI Computer Use Preview",
    description: "GPT models including GPT-4, GPT-3.5-turbo",
  },
  {
    value: "anthropic",
    label: "Anthropic",
    description: "Claude models including Claude 3 Opus, Sonnet, and Haiku",
  },
  {
    value: "gemini",
    label: "Google Gemini Computer Use",
    description: "Google's Gemini 2.5 with Computer Use for browser automation",
  },
];

const modelSchema = Yup.object().shape({
  name: Yup.string()
    .min(2, "Name must be at least 2 characters")
    .max(100, "Name must be less than 100 characters")
    .required("Name is required"),
  type: Yup.string()
    .oneOf(["openai", "anthropic", "gemini"], "Invalid model type")
    .required("Model type is required"),
  description: Yup.string()
    .min(10, "Description must be at least 10 characters")
    .max(500, "Description must be less than 500 characters")
    .required("Description is required"),
  api_key: Yup.string()
    .min(8, "API key must be at least 8 characters")
    .required("API key is required"),
});

export default function ModelForm({
  open,
  onClose,
  model,
  onSuccess,
  onError,
}: ModelFormProps) {
  const createModelMutation = useCreateModel({
    onSuccess: (createdModel) => {
      onSuccess?.(createdModel);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });
  const updateModelMutation = useUpdateModel({
    onSuccess: (updatedModel) => {
      onSuccess?.(updatedModel);
      onClose();
    },
    onError: (error) => {
      onError?.(error);
    },
  });
  const [showApiKey, setShowApiKey] = useState(false);

  const isEditing = !!model;
  const isLoading =
    createModelMutation.isPending || updateModelMutation.isPending;

  const initialValues = {
    name: model?.name || "",
    type: model?.type || ("" as ModelType),
    description: model?.description || "",
    api_key: model?.api_key || "",
  };

  const handleSubmit = (values: typeof initialValues) => {
    if (isEditing) {
      updateModelMutation.mutate({ id: model.id, ...values });
    } else {
      createModelMutation.mutate(values);
    }
  };

  return (
    <Formik
      initialValues={initialValues}
      validationSchema={modelSchema}
      onSubmit={handleSubmit}
      enableReinitialize
    >
      {({ errors, touched, isValid, dirty }) => (
        <SidebarForm
          open={open}
          onClose={onClose}
          title={isEditing ? "Edit Model" : "Add New Model"}
          width={480}
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
                form="model-form"
                variant="contained"
                disabled={isLoading || !isValid || (!dirty && !isEditing)}
                size="large"
                sx={{ minWidth: 120 }}
              >
                {isLoading
                  ? isEditing
                    ? "Updating..."
                    : "Adding..."
                  : isEditing
                    ? "Update Model"
                    : "Add Model"}
              </Button>
            </Box>
          }
        >
          <Form id="model-form">
            <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {/* Model Name Field */}
              <Field name="name">
                {({ field }: { field: any }) => (
                  <Box>
                    <Typography
                      variant="subtitle2"
                      sx={{ mb: 1, fontWeight: 600 }}
                    >
                      Model Name
                    </Typography>
                    <TextField
                      {...field}
                      fullWidth
                      placeholder="e.g., Computer Use Preview, Claude Sonnet 4"
                      error={touched.name && !!errors.name}
                      helperText={
                        touched.name && errors.name
                          ? errors.name
                          : "A descriptive name for this model configuration"
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

              {/* Model Type Field */}
              <Field name="type">
                {({ field, form }: { field: any; form: any }) => (
                  <Box>
                    <Typography
                      variant="subtitle2"
                      sx={{ mb: 1, fontWeight: 600 }}
                    >
                      Model Type
                    </Typography>
                    <TextField
                      select
                      fullWidth
                      name={field.name}
                      value={field.value || ""}
                      onChange={(event) => {
                        form.setFieldValue("type", event.target.value);
                      }}
                      onBlur={field.onBlur}
                      error={touched.type && !!errors.type}
                      helperText={
                        touched.type && errors.type
                          ? errors.type
                          : "Select the AI model provider"
                      }
                      disabled={isLoading}
                      sx={{
                        "& .MuiInputBase-root": {
                          fontSize: "0.95rem",
                        },
                      }}
                    >
                      <MenuItem value="">
                        <em>Select model type...</em>
                      </MenuItem>
                      {modelTypes.map((type) => (
                        <MenuItem key={type.value} value={type.value}>
                          <Box>
                            <Typography
                              variant="body1"
                              sx={{ fontWeight: 500 }}
                            >
                              {type.label}
                            </Typography>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{ display: "block", mt: 0.5 }}
                            >
                              {type.description}
                            </Typography>
                          </Box>
                        </MenuItem>
                      ))}
                    </TextField>
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
                      placeholder="Describe the model's capabilities, use cases, and any specific configuration details...

Examples:
• Computer Use Preview for advanced computer interaction
• Claude Sonnet 4 for reasoning and analysis"
                      error={touched.description && !!errors.description}
                      helperText={
                        touched.description && errors.description
                          ? errors.description
                          : `${(field.value || "").length}/500 characters - Describe what this model is best suited for`
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

              {/* API Key Field */}
              <Field name="api_key">
                {({ field }: { field: any }) => (
                  <Box>
                    <Typography
                      variant="subtitle2"
                      sx={{ mb: 1, fontWeight: 600 }}
                    >
                      API Key
                    </Typography>
                    <TextField
                      {...field}
                      fullWidth
                      type={showApiKey ? "text" : "password"}
                      placeholder="Enter your API key..."
                      error={touched.api_key && !!errors.api_key}
                      helperText={
                        touched.api_key && errors.api_key
                          ? errors.api_key
                          : "Your API key will be stored securely and used for model authentication"
                      }
                      disabled={isLoading}
                      value={field.value || ""}
                      InputProps={{
                        endAdornment: (
                          <InputAdornment position="end">
                            <IconButton
                              onClick={() => setShowApiKey(!showApiKey)}
                              edge="end"
                              sx={{
                                color: "text.secondary",
                                "&:hover": {
                                  backgroundColor: "action.hover",
                                },
                              }}
                            >
                              {showApiKey ? <VisibilityOff /> : <Visibility />}
                            </IconButton>
                          </InputAdornment>
                        ),
                      }}
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
            </Box>
          </Form>
        </SidebarForm>
      )}
    </Formik>
  );
}
