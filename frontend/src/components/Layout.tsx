import type { PropsWithChildren } from "react";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import CssBaseline from "@mui/material/CssBaseline";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Avatar from "@mui/material/Avatar";
import Badge from "@mui/material/Badge";
import { useNavigate, useLocation } from "react-router-dom";
import FitnessCenterIcon from "@mui/icons-material/FitnessCenter";
import AssignmentIcon from "@mui/icons-material/Assignment";
import ModelTrainingIcon from "@mui/icons-material/ModelTraining";
import BatchIcon from "@mui/icons-material/List";
import LeaderboardIcon from "@mui/icons-material/Leaderboard";
import PlaygroundIcon from "@mui/icons-material/PlayArrow";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import LogoutIcon from "@mui/icons-material/Logout";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import NotificationsIcon from "@mui/icons-material/Notifications";
import InfoIcon from "@mui/icons-material/Info";
import Tooltip from "@mui/material/Tooltip";
import ThemeToggle from "./common/ThemeToggle";
import { useTheme } from "../contexts/ThemeContext";
import { useAuth } from "../contexts/AuthContext";
import { useState } from "react";
import NotificationCenter from "./NotificationCenter";
import { useReadyReports } from "../hooks/useReadyReports";
import { DownloadManager } from "./DownloadManager";

const drawerWidth = 240;

const items = [
  { label: "Gyms", path: "/gyms", icon: <FitnessCenterIcon /> },
  { label: "Tasks", path: "/tasks", icon: <AssignmentIcon /> },
  { label: "Models", path: "/models", icon: <ModelTrainingIcon /> },
  { label: "Batches", path: "/batches", icon: <BatchIcon /> },
  { label: "Playground", path: "/runs", icon: <PlaygroundIcon /> },
  { label: "Leaderboard", path: "/leaderboard", icon: <LeaderboardIcon /> },
];

export default function Layout({ children }: PropsWithChildren) {
  const navigate = useNavigate();
  const location = useLocation();
  const { mode } = useTheme();
  const { user, logout, isAdmin } = useAuth();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [notificationOpen, setNotificationOpen] = useState(false);
  
  // Fetch ready reports for notification badge (only if user is authenticated)
  const { data: readyReports } = useReadyReports(
    { enabled: !!user }, // Only fetch if user is logged in
    30000 // Poll every 30 seconds
  );
  
  // Hide drawer on report preview page
  const hideDrawer = location.pathname.includes("/report-preview");

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = () => {
    logout();
    handleMenuClose();
    navigate("/login");
  };

  const handleAdminPanel = () => {
    handleMenuClose();
    navigate("/admin");
  };

  return (
    <Box sx={{ display: "flex" }}>
      <CssBaseline />
      <AppBar
        position="fixed"
        sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}
      >
        <Toolbar>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            RL Gym Harness
          </Typography>
          <Tooltip
            title="RL Gym Harness is a task automation system that orchestrates AI agents (OpenAI, Anthropic, Gemini) to complete tasks in gym environments. It manages task execution, tracks agent performance, verifies task completion, and generates detailed reports. You create gyms (testing environments), define tasks, and run batches to evaluate how well AI agents perform those tasks."
            arrow
            placement="bottom"
          >
            <IconButton size="large" color="inherit" sx={{ mr: 1 }}>
              <InfoIcon />
            </IconButton>
          </Tooltip>
          <ThemeToggle />
          
          {/* Notification Icon */}
          <IconButton
            size="large"
            onClick={() => setNotificationOpen(true)}
            color="inherit"
            sx={{ ml: 1 }}
          >
            <Badge 
              badgeContent={readyReports?.unread_count || 0} 
              color="success"
              max={99}
            >
              <NotificationsIcon />
            </Badge>
          </IconButton>
          
          <Box sx={{ ml: 1, display: "flex", alignItems: "center", gap: 1 }}>
            <Typography
              variant="body2"
              sx={{ display: { xs: "none", sm: "block" } }}
            >
              {user?.name}
            </Typography>
            <IconButton size="large" onClick={handleMenuOpen} color="inherit">
              <Avatar src={user?.picture} sx={{ width: 32, height: 32 }}>
                {user?.name?.charAt(0)?.toUpperCase()}
              </Avatar>
            </IconButton>
            <Menu
              anchorEl={anchorEl}
              open={Boolean(anchorEl)}
              onClose={handleMenuClose}
              anchorOrigin={{
                vertical: "bottom",
                horizontal: "right",
              }}
              transformOrigin={{
                vertical: "top",
                horizontal: "right",
              }}
            >
              <MenuItem onClick={handleMenuClose}>
                <ListItemIcon>
                  <AccountCircleIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary={user?.email} />
              </MenuItem>
              {isAdmin && (
                <MenuItem onClick={handleAdminPanel}>
                  <ListItemIcon>
                    <AdminPanelSettingsIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText primary="Admin Panel" />
                </MenuItem>
              )}
              <Divider />
              <MenuItem onClick={handleLogout}>
                <ListItemIcon>
                  <LogoutIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Logout" />
              </MenuItem>
            </Menu>
          </Box>
        </Toolbar>
      </AppBar>
      {!hideDrawer && (
        <Drawer
          variant="permanent"
          sx={{
            width: drawerWidth,
            flexShrink: 0,
            [`& .MuiDrawer-paper`]: {
              width: drawerWidth,
              boxSizing: "border-box",
            },
          }}
        >
          <Toolbar />
          <Box sx={{ overflow: "auto" }}>
            <List>
              {(isAdmin
                ? items
                : items.filter(
                    (item) => item.path === "/tasks" || item.path === "/batches",
                  )
              ).map((item) => (
                <ListItem key={item.path} disablePadding>
                  <ListItemButton
                    selected={location.pathname === item.path}
                    onClick={() => navigate(item.path)}
                  >
                    <ListItemIcon>{item.icon}</ListItemIcon>
                    <ListItemText primary={item.label} />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
            <Divider />
          </Box>
        </Drawer>
      )}
      
      {/* Notification Center */}
      <NotificationCenter
        open={notificationOpen}
        onClose={() => setNotificationOpen(false)}
      />
      
      {/* Download Manager */}
      <DownloadManager />
      
      <Box component="main" sx={{ flexGrow: 1, pt: 1, px: hideDrawer ? 0 : 4, pb: 3 }}>
        <Toolbar />
        <Box
          sx={{
            maxWidth: hideDrawer ? "100%" : 1600,
            mx: "auto",
            px: hideDrawer ? 0 : 3,
            mt: 2,
            ...(mode === "light" && !hideDrawer && {
              borderRadius: 2,
              backgroundColor: "#ffffff",
            }),
          }}
        >
          {children}
        </Box>
      </Box>
    </Box>
  );
}
