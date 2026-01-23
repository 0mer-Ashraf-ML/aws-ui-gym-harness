import {
  Box,
  Typography,
  Paper,
  useTheme,
  alpha,
} from '@mui/material';
import {
  Analytics as InsightsIcon,
} from '@mui/icons-material';

interface ExecutionInsightsProps {
  evalInsights?: string | null;
}

export default function ExecutionInsights({
  evalInsights,
}: ExecutionInsightsProps) {
  const theme = useTheme();

  // Don't render if no insights are available
  if (!evalInsights?.trim()) {
    return null;
  }

  return (
    <Box sx={{ mt: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
        <InsightsIcon sx={{ fontSize: 16, color: theme.palette.primary.main }} />
        <Typography variant="subtitle2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
          Execution Insights
        </Typography>
      </Box>
      
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
          {evalInsights}
        </Typography>
      </Paper>
    </Box>
  );
}
