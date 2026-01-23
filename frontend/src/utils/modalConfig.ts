// Shared modal configurations for consistent sizing across the application

export const modalSizes = {
  // Small modals for confirmations, alerts, simple forms
  small: {
    maxWidth: "xs" as const,
  },

  // Medium modals for details, forms, content viewing
  medium: {
    maxWidth: "sm" as const,
    fullWidth: true,
  },

  // Large modals for complex content, previews, wide layouts
  large: {
    maxWidth: "lg" as const,
    fullWidth: true,
  },
} as const;

// Specific modal type configurations
export const modalConfig = {
  // Delete confirmation modals
  deleteConfirmation: modalSizes.medium,

  // Details/view modals
  details: modalSizes.medium,

  // Form modals
  form: modalSizes.medium,

  // Preview modals (files, images, etc.)
  preview: modalSizes.large,
} as const;

// Type exports for TypeScript support
export type ModalSize = keyof typeof modalSizes;
export type ModalType = keyof typeof modalConfig;
