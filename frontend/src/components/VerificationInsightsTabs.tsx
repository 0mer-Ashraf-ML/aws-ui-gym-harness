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
  CheckCircle as VerificationIcon,
  Analytics as InsightsIcon,
} from '@mui/icons-material';

interface VerificationInsightsTabsProps {
  verificationComments?: string;
  evalInsights?: string;
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
      id={`verification-insights-tabpanel-${index}`}
      aria-labelledby={`verification-insights-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 2 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

function a11yProps(index: number) {
  return {
    id: `verification-insights-tab-${index}`,
    'aria-controls': `verification-insights-tabpanel-${index}`,
  };
}

export default function VerificationInsightsTabs({
  verificationComments,
  evalInsights,
}: VerificationInsightsTabsProps) {
  const theme = useTheme();
  const [value, setValue] = useState(0);

  const handleChange = (_event: React.SyntheticEvent, newValue: number) => {
    setValue(newValue);
  };

  // Don't render if neither verification comments nor insights are available
  if (!verificationComments?.trim() && !evalInsights?.trim()) {
    return null;
  }

  // Always show tabs for consistent UI (even with single content)
  const hasVerification = verificationComments?.trim();
  const hasInsights = evalInsights?.trim();
  
  // Determine which tabs to show
  const tabs = [];
  if (hasVerification) tabs.push({ type: 'verification', label: 'Verification', icon: VerificationIcon, color: theme.palette.success.main });
  if (hasInsights) tabs.push({ type: 'insights', label: 'Insights', icon: InsightsIcon, color: theme.palette.primary.main });
  
  return (
    <Box sx={{ mt: 2 }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={value}
          onChange={handleChange}
          aria-label="verification and insights tabs"
          sx={{
            minHeight: 40,
            '& .MuiTab-root': {
              textTransform: 'none',
              fontWeight: 600,
              minHeight: 40,
              fontSize: '0.875rem',
              py: 1,
            },
            '& .MuiTabs-indicator': {
              height: 2,
            },
          }}
        >
          {tabs.map((tab, index) => (
            <Tab
              key={tab.type}
              icon={<tab.icon sx={{ fontSize: 16 }} />}
              label={tab.label}
              {...a11yProps(index)}
            />
          ))}
        </Tabs>
      </Box>
      {tabs.map((tab, index) => (
        <TabPanel key={tab.type} value={value} index={index}>
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              backgroundColor: alpha(tab.color, 0.02),
              border: `1px solid ${alpha(tab.color, 0.15)}`,
              borderRadius: 1,
            }}
          >
            <Typography
              variant="body2"
              sx={{ 
                whiteSpace: "pre-line",
                lineHeight: 1.5,
                fontSize: '0.875rem',
              }}
            >
              {tab.type === 'verification' ? verificationComments : evalInsights}
            </Typography>
          </Paper>
        </TabPanel>
      ))}
    </Box>
  );
}
