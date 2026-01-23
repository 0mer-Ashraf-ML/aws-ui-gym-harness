import { createTheme } from "@mui/material/styles";
import type { ThemeOptions } from "@mui/material/styles";

declare module "@mui/material/styles" {
  interface Theme {
    custom: {
      colors: {
        mono: {
          50: string;
          100: string;
          200: string;
          300: string;
          400: string;
          500: string;
          600: string;
          700: string;
          800: string;
          900: string;
          950: string;
        };
        accent: {
          blue: {
            50: string;
            100: string;
            200: string;
            300: string;
            400: string;
            500: string;
            600: string;
            700: string;
            800: string;
            900: string;
          };
          green: {
            50: string;
            100: string;
            200: string;
            300: string;
            400: string;
            500: string;
            600: string;
            700: string;
            800: string;
            900: string;
          };
          orange: {
            50: string;
            100: string;
            200: string;
            300: string;
            400: string;
            500: string;
            600: string;
            700: string;
            800: string;
            900: string;
          };
          red: {
            50: string;
            100: string;
            200: string;
            300: string;
            400: string;
            500: string;
            600: string;
            700: string;
            800: string;
            900: string;
          };
        };
        gradients: {
          light: string[];
          dark: string[];
        };
      };
    };
  }

  interface ThemeOptions {
    custom?: {
      colors?: {
        mono?: {
          50?: string;
          100?: string;
          200?: string;
          300?: string;
          400?: string;
          500?: string;
          600?: string;
          700?: string;
          800?: string;
          900?: string;
          950?: string;
        };
        accent?: {
          blue?: {
            50?: string;
            100?: string;
            200?: string;
            300?: string;
            400?: string;
            500?: string;
            600?: string;
            700?: string;
            800?: string;
            900?: string;
          };
          green?: {
            50?: string;
            100?: string;
            200?: string;
            300?: string;
            400?: string;
            500?: string;
            600?: string;
            700?: string;
            800?: string;
            900?: string;
          };
          orange?: {
            50?: string;
            100?: string;
            200?: string;
            300?: string;
            400?: string;
            500?: string;
            600?: string;
            700?: string;
            800?: string;
            900?: string;
          };
          red?: {
            50?: string;
            100?: string;
            200?: string;
            300?: string;
            400?: string;
            500?: string;
            600?: string;
            700?: string;
            800?: string;
            900?: string;
          };
        };
        gradients?: {
          light?: string[];
          dark?: string[];
        };
      };
    };
  }
}

const customColors = {
  mono: {
    50: "#ffffff",
    100: "#f8f9fa",
    200: "#e9ecef",
    300: "#dee2e6",
    400: "#ced4da",
    500: "#adb5bd",
    600: "#6c757d",
    700: "#495057",
    800: "#262626",
    900: "#161616",
    950: "#000000",
  },
  accent: {
    blue: {
      50: "#f0f9ff",
      100: "#e0f2fe",
      200: "#bae6fd",
      300: "#7dd3fc",
      400: "#38bdf8",
      500: "#0ea5e9",
      600: "#0284c7",
      700: "#0369a1",
      800: "#075985",
      900: "#0c4a6e",
    },
    green: {
      50: "#f0fdf4",
      100: "#dcfce7",
      200: "#bbf7d0",
      300: "#86efac",
      400: "#4ade80",
      500: "#016239",
      600: "#15803d",
      700: "#166534",
      800: "#14532d",
      900: "#052e16",
    },
    orange: {
      50: "#fff7ed",
      100: "#ffedd5",
      200: "#fed7aa",
      300: "#fdba74",
      400: "#fb923c",
      500: "#f97316",
      600: "#ea580c",
      700: "#c2410c",
      800: "#9a3412",
      900: "#7c2d12",
    },
    red: {
      50: "#fef2f2",
      100: "#fee2e2",
      200: "#fecaca",
      300: "#fca5a5",
      400: "#f87171",
      500: "#ef4444",
      600: "#dc2626",
      700: "#b91c1c",
      800: "#991b1b",
      900: "#7f1d1d",
    },
  },
  gradients: {
    light: [
      "linear-gradient(135deg, #f8f9ff 0%, #e8efff 30%, #6078A4 70%, #2F4B80 100%)",
      "linear-gradient(135deg, #f5f7ff 0%, #dde6ff 30%, #5a7299 70%, #0B0F2B 100%)",
      "linear-gradient(135deg, #ffffff 0%, #f0f4ff 30%, #6078A4 50%, #2F4B80 100%)",
      "linear-gradient(135deg, #fafbff 0%, #e5ebff 30%, #4a6594 70%, #0B0F2B 100%)",
      "linear-gradient(135deg, #f9faff 0%, #e0e8ff 30%, #6078A4 60%, #2F4B80 100%)",
      "linear-gradient(135deg, #ffffff 0%, #f2f6ff 30%, #556a8f 70%, #0B0F2B 100%)",
      "linear-gradient(135deg, #f7f9ff 0%, #dce4ff 30%, #6078A4 50%, #2F4B80 100%)",
      "linear-gradient(135deg, #fefefd 0%, #eff5ff 30%, #5e7ca1 70%, #0B0F2B 100%)",
      "linear-gradient(135deg, #fbfcff 0%, #e7edff 30%, #6078A4 60%, #2F4B80 100%)",
      "linear-gradient(135deg, #ffffff 0%, #f1f7ff 30%, #52678a 70%, #0B0F2B 100%)",
    ],
    dark: [
      "linear-gradient(135deg, #1a1d2e 0%, #2d3748 30%, #6078A4 70%, #9fb7d3 100%)",
      "linear-gradient(135deg, #0B0F2B 0%, #1e293b 30%, #5a7299 70%, #94a3b8 100%)",
      "linear-gradient(135deg, #171923 0%, #2d3748 30%, #6078A4 50%, #9fb7d3 100%)",
      "linear-gradient(135deg, #0B0F2B 0%, #1e293b 30%, #4a6594 70%, #8fabc9 100%)",
      "linear-gradient(135deg, #1a1d2e 0%, #2d3748 30%, #6078A4 60%, #9fb7d3 100%)",
      "linear-gradient(135deg, #0B0F2B 0%, #1e293b 30%, #556a8f 70%, #8fabc9 100%)",
      "linear-gradient(135deg, #171923 0%, #2d3748 30%, #6078A4 50%, #9fb7d3 100%)",
      "linear-gradient(135deg, #0B0F2B 0%, #1e293b 30%, #5e7ca1 70%, #94a3b8 100%)",
      "linear-gradient(135deg, #1a1d2e 0%, #2d3748 30%, #6078A4 60%, #9fb7d3 100%)",
      "linear-gradient(135deg, #0B0F2B 0%, #1e293b 30%, #52678a 70%, #8fabc9 100%)",
    ],
  },
};

// Sidebar color for form submit buttons - using new palette
const sidebarColor = "#161616"; // Dark theme color
const sidebarColorLight = "#363636"; // Lighter theme color for cancel buttons

const createCustomTheme = (mode: "light" | "dark"): ThemeOptions => ({
  palette: {
    mode,
    primary: {
      main: customColors.accent.green[500],
      light: customColors.accent.green[400],
      dark: customColors.accent.green[600],
    },
    secondary: {
      main: customColors.accent.blue[500],
      light: customColors.accent.blue[400],
      dark: customColors.accent.blue[600],
    },
    error: {
      main: customColors.accent.red[500],
      light: customColors.accent.red[400],
      dark: customColors.accent.red[600],
    },
    warning: {
      main: customColors.accent.orange[500],
      light: customColors.accent.orange[400],
      dark: customColors.accent.orange[600],
    },
    info: {
      main: customColors.accent.green[500],
      light: customColors.accent.green[400],
      dark: customColors.accent.green[600],
    },
    success: {
      main: customColors.accent.green[500],
      light: customColors.accent.green[400],
      dark: customColors.accent.green[600],
    },
    background: {
      default: mode === "light" ? "#ffffff" : customColors.mono[900],
      paper: mode === "light" ? "#ffffff" : "#212121",
    },
    text: {
      primary:
        mode === "light" ? customColors.mono[900] : customColors.mono[100],
      secondary:
        mode === "light" ? customColors.mono[600] : customColors.mono[400],
    },
    divider: mode === "light" ? customColors.mono[200] : "#2E2E2E",
  },
  typography: {
    fontFamily: '"Inter", system-ui, sans-serif',
    fontSize: 13,
    h1: {
      fontSize: "1.75rem",
      fontWeight: 700,
    },
    h2: {
      fontSize: "1.5rem",
      fontWeight: 600,
    },
    h3: {
      fontSize: "1.25rem",
      fontWeight: 600,
    },
    h4: {
      fontSize: "1.1rem",
      fontWeight: 600,
    },
    h5: {
      fontSize: "1rem",
      fontWeight: 600,
    },
    h6: {
      fontSize: "0.9rem",
      fontWeight: 600,
    },
    body1: {
      fontSize: "0.875rem",
    },
    body2: {
      fontSize: "0.8125rem",
    },
    caption: {
      fontSize: "0.75rem",
    },
    button: {
      fontSize: "0.8125rem",
      textTransform: "none",
      fontWeight: 500,
    },
  },
  shape: {
    borderRadius: 8,
  },
  shadows: [
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
    "none",
  ],
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          transition: "background-color 0.2s ease, color 0.2s ease",
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
          fontWeight: 500,
          borderRadius: 6,
          padding: "6px 12px",
          boxShadow: "none",
          border: `1px solid ${mode === "light" ? customColors.mono[300] : "#2E2E2E"}`,
          "&:hover": {
            boxShadow: "none",
            borderColor: mode === "light" ? customColors.mono[300] : "#2E2E2E",
          },
        },
        outlined: {
          color: "#ffffff",
          "&:hover": {
            color: "#ffffff",
          },
        },
      },
      variants: [
        {
          props: { variant: "contained" },
          style: {
            backgroundColor: customColors.accent.green[500], // Primary green
            color: "#ffffff",
            "&:hover": {
              backgroundColor: customColors.accent.green[600],
            },
            "&:disabled": {
              backgroundColor:
                mode === "light"
                  ? customColors.mono[300]
                  : customColors.mono[700],
              color:
                mode === "light"
                  ? customColors.mono[500]
                  : customColors.mono[400],
            },
          },
        },
        {
          props: { variant: "contained", color: "success" },
          style: {
            backgroundColor: "#016239", // Create button background
            color: "#ffffff", // White text
            "&:hover": {
              backgroundColor: "#014a2b",
            },
            "&:disabled": {
              backgroundColor:
                mode === "light"
                  ? customColors.mono[300]
                  : customColors.mono[700],
              color:
                mode === "light"
                  ? customColors.mono[500]
                  : customColors.mono[400],
            },
          },
        },
        {
          props: { variant: "outlined" },
          style: {
            borderColor: mode === "light" ? customColors.mono[300] : "#2E2E2E",
            color: mode === "light" ? customColors.mono[700] : "#ffffff",
            backgroundColor: "transparent",
            "&:hover": {
              borderColor:
                mode === "light" ? customColors.mono[300] : "#2E2E2E",
              backgroundColor:
                mode === "light"
                  ? "rgba(0, 0, 0, 0.04)"
                  : "rgba(255, 255, 255, 0.08)",
              color: mode === "light" ? customColors.mono[700] : "#ffffff",
            },
          },
        },
        {
          props: { variant: "contained", color: "error" },
          style: {
            backgroundColor: "#ef4444", // Red background
            color: "#ffffff", // White text
            "&:hover": {
              backgroundColor: "#dc2626",
            },
            "&:disabled": {
              backgroundColor:
                mode === "light"
                  ? customColors.mono[300]
                  : customColors.mono[700],
              color:
                mode === "light"
                  ? customColors.mono[500]
                  : customColors.mono[400],
            },
          },
        },
        {
          props: { className: "form-submit" },
          style: {
            backgroundColor: sidebarColor, // Sidebar color for form submit buttons
            color: "#ffffff",
            "&:hover": {
              backgroundColor: "#162640", // Darker shade of Midnight Blue
            },
            "&:disabled": {
              backgroundColor:
                mode === "light"
                  ? customColors.mono[300]
                  : customColors.mono[700],
              color:
                mode === "light"
                  ? customColors.mono[500]
                  : customColors.mono[400],
            },
          },
        },
        {
          props: { className: "cancel-button" },
          style: {
            backgroundColor: sidebarColorLight, // Lighter sidebar color for cancel
            color: "#ffffff",
            "&:hover": {
              backgroundColor: "#455a70", // Darker shade of Dusty Blue
            },
            "&:disabled": {
              backgroundColor:
                mode === "light"
                  ? customColors.mono[300]
                  : customColors.mono[700],
              color:
                mode === "light"
                  ? customColors.mono[500]
                  : customColors.mono[400],
            },
          },
        },
      ],
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: mode === "light" ? "#ffffff" : "#212121",
          boxShadow: "none",
          borderRadius: 6,
          border: `1px solid ${mode === "light" ? customColors.mono[300] : "#2E2E2E"}`,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: mode === "light" ? "#F8F8F7" : "#161616",
          border: mode === "light" ? "none" : `1px solid #2E2E2E`,
          boxShadow: "none",
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          "& .MuiOutlinedInput-root": {
            borderRadius: 4,
            fontSize: "0.875rem",
            backgroundColor: mode === "light" ? "#ffffff" : "#1E1E1E",
            "& fieldset": {
              borderColor:
                mode === "light" ? customColors.mono[300] : "#2E2E2E",
            },
            "&:hover fieldset": {
              borderColor:
                mode === "light" ? customColors.mono[400] : "#2E2E2E",
            },
            "&.Mui-focused fieldset": {
              borderColor:
                mode === "light" ? customColors.mono[300] : "#2E2E2E",
            },
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 6,
        },
      },
    },
    MuiAppBar: {
      defaultProps: {
        elevation: 0,
      },
      styleOverrides: {
        root: {
          boxShadow: "none",
          borderBottom: mode === "light" ? "none" : `1px solid #2E2E2E`,
          backgroundColor: mode === "light" ? "#F8F8F7" : "#161616",
          color:
            mode === "light" ? customColors.mono[900] : customColors.mono[100],
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 500,
        },
        standardSuccess: {
          backgroundColor: "#dcfce7", // Light green background
          color: "#166534", // Dark green text
          border: `1px solid #bbf7d0`,
          "& .MuiAlert-icon": {
            color: "#166534",
          },
        },
        standardError: {
          backgroundColor: "#fef2f2", // Light red background
          color: "#991b1b", // Dark red text
          border: `1px solid #fecaca`,
          "& .MuiAlert-icon": {
            color: "#991b1b",
          },
        },
        filledSuccess: {
          backgroundColor: "#016239",
          color: "#ffffff",
        },
        filledError: {
          backgroundColor: "#ef4444",
          color: "#ffffff",
        },
        outlinedSuccess: {
          backgroundColor: mode === "light" ? "#f0fdf4" : "#0f1f13",
          color: mode === "light" ? "#166534" : "#016239",
          borderColor: "#016239",
        },
        outlinedError: {
          backgroundColor: mode === "light" ? "#fef2f2" : "#1f0f0f",
          color: mode === "light" ? "#991b1b" : "#ef4444",
          borderColor: "#ef4444",
        },
      },
    },
    MuiSnackbar: {
      styleOverrides: {
        root: {
          "& .MuiAlert-root": {
            borderRadius: 8,
            fontWeight: 500,
          },
        },
      },
    },
    MuiListItem: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          margin: "2px 0",
          "&.Mui-selected": {
            backgroundColor:
              mode === "light" ? customColors.mono[200] : "#202020",
            "&:hover": {
              backgroundColor:
                mode === "light" ? customColors.mono[200] : "#252525",
            },
          },
          "&:hover": {
            backgroundColor:
              mode === "light" ? customColors.mono[100] : "#1A1A1A",
          },
        },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 6,
          margin: "2px 0",
          "&.Mui-selected": {
            backgroundColor:
              mode === "light" ? customColors.mono[200] : "#202020",
            "&:hover": {
              backgroundColor:
                mode === "light" ? customColors.mono[300] : "#252525",
            },
          },
          "&:hover": {
            backgroundColor:
              mode === "light" ? customColors.mono[100] : "#1A1A1A",
          },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          backgroundColor: mode === "light" ? "#ffffff" : "#202020",
          border: `1px solid ${mode === "light" ? customColors.mono[300] : "#2E2E2E"}`,
        },
      },
    },
  },
  custom: {
    colors: customColors,
  },
});

export const lightTheme = createTheme(createCustomTheme("light"));
export const darkTheme = createTheme(createCustomTheme("dark"));
