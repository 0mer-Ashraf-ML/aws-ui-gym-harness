import React, { useState } from 'react';
import {
  Box,
  Tabs,
  Tab,
  Typography,
  Paper,
  useTheme,
  alpha,
} from '@mui/material';
import {
  Analytics as InsightsIcon,
} from '@mui/icons-material';

interface BatchInsightsTabsProps {
  evalInsights?: { [key: string]: string } | null;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`batch-insights-tabpanel-${index}`}
      aria-labelledby={`batch-insights-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

function a11yProps(index: number) {
  return {
    id: `batch-insights-tab-${index}`,
    'aria-controls': `batch-insights-tabpanel-${index}`,
  };
}

export default function BatchInsightsTabs({
  evalInsights,
}: BatchInsightsTabsProps) {
  const theme = useTheme();
  const [value, setValue] = useState(0);

  const handleChange = (_event: React.SyntheticEvent, newValue: number) => {
    setValue(newValue);
  };

  // Don't render if no insights are available
  if (!evalInsights || Object.keys(evalInsights).length === 0) {
    return null;
  }

  const modelNames = Object.keys(evalInsights);

  // Always show tabs for consistent UI (even with single model)
  return (
    <Box sx={{ mt: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
        <InsightsIcon sx={{ fontSize: 16, color: theme.palette.primary.main }} />
        <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
          Batch Insights
        </Typography>
      </Box>
      
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={value}
          onChange={handleChange}
          aria-label="batch insights tabs"
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            minHeight: 40,
            '& .MuiTab-root': {
              textTransform: 'none',
              fontWeight: 600,
              minHeight: 40,
              fontSize: '0.875rem',
              py: 1,
              '&.Mui-selected': {
                color: theme.palette.primary.main,
              },
            },
            '& .MuiTabs-indicator': {
              backgroundColor: theme.palette.primary.main,
              height: 2,
            },
          }}
        >
          {modelNames.map((modelName, index) => (
            <Tab
              key={modelName}
              icon={<InsightsIcon sx={{ fontSize: 16 }} />}
              label={modelName.toUpperCase()}
              {...a11yProps(index)}
            />
          ))}
        </Tabs>
      </Box>
      
      {modelNames.map((modelName, index) => (
        <TabPanel key={modelName} value={value} index={index}>
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              backgroundColor: alpha(theme.palette.primary.main, 0.02),
              border: `1px solid ${alpha(theme.palette.primary.main, 0.15)}`,
              borderRadius: 1,
            }}
          >
            <Typography
              variant="body2"
              sx={{ 
                whiteSpace: "pre-line",
                lineHeight: 1.5,
                color: 'text.primary',
                fontSize: '0.875rem',
                '& p': {
                  margin: '0 0 0.5em 0',
                  '&:last-child': {
                    marginBottom: 0
                  }
                }
              }}
            >
              {evalInsights[modelName]}
            </Typography>
          </Paper>
        </TabPanel>
      ))}
    </Box>
  );
}
