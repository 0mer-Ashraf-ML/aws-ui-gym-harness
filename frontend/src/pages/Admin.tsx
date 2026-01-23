import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  IconButton,
  Alert,
  CircularProgress,
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
} from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { authService } from '../services/auth';
import DomainManagement from '../components/DomainManagement';
import * as Types from '../types';

const Admin: React.FC = () => {
  const { token, isAdmin } = useAuth();
  const [users, setUsers] = useState<Types.User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [whitelistDialogOpen, setWhitelistDialogOpen] = useState(false);
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserIsAdmin, setNewUserIsAdmin] = useState(false);
  const [activeTab, setActiveTab] = useState(0);

  useEffect(() => {
    if (!isAdmin) return;
    loadUsers();
  }, [isAdmin]);

  // Additional safety check - redirect non-admin users
  if (!isAdmin) {
    return (
      <Container maxWidth="lg">
        <Box sx={{ mt: 4, textAlign: 'center' }}>
          <Typography variant="h4" component="h1" color="error" sx={{ mb: 2 }}>
            Access Denied
          </Typography>
          <Typography variant="body1" color="text.secondary">
            You need administrator privileges to access this page.
          </Typography>
        </Box>
      </Container>
    );
  }

  const loadUsers = async () => {
    if (!token) return;
    
    try {
      setLoading(true);
      setError(null);
      const userList = await authService.getAllUsers(token);
      setUsers(userList);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const handleWhitelistUser = async () => {
    if (!token || !newUserEmail.trim()) return;

    try {
      setError(null);
      await authService.whitelistUser(token, newUserEmail.trim(), newUserIsAdmin);
      setSuccess(`User ${newUserEmail} has been whitelisted successfully`);
      setWhitelistDialogOpen(false);
      setNewUserEmail('');
      setNewUserIsAdmin(false);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to whitelist user');
    }
  };

  const handleRemoveFromWhitelist = async (email: string) => {
    if (!token) return;

    try {
      setError(null);
      await authService.removeFromWhitelist(token, email);
      setSuccess(`User ${email} has been removed from whitelist`);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove user from whitelist');
    }
  };

  if (!isAdmin) {
    return (
      <Container maxWidth="lg">
        <Box sx={{ mt: 4 }}>
          <Alert severity="error">
            You need administrator privileges to access this page.
          </Alert>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg">
      <Box sx={{ mt: 4 }}>
        <Typography variant="h4" component="h1" sx={{ mb: 3 }}>
          Admin Panel
        </Typography>
        
        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
          <Tabs value={activeTab} onChange={(_, newValue) => setActiveTab(newValue)}>
            <Tab label="User Management" />
            <Tab label="Domain Management" />
          </Tabs>
        </Box>

        {activeTab === 0 && (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
              <Typography variant="h5" component="h2">
                User Management
              </Typography>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setWhitelistDialogOpen(true)}
              >
                Whitelist User
              </Button>
            </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {success && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}

        <Paper>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Email</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Admin</TableCell>
                  <TableCell>Last Login</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={6} align="center">
                      <CircularProgress />
                    </TableCell>
                  </TableRow>
                ) : users.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} align="center">
                      No users found
                    </TableCell>
                  </TableRow>
                ) : (
                  users.map((user) => (
                    <TableRow key={user.uuid}>
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="body2">{user.name}</Typography>
                        </Box>
                      </TableCell>
                      <TableCell>{user.email}</TableCell>
                      <TableCell>
                        <Chip
                          label={user.is_whitelisted ? 'Whitelisted' : 'Not Whitelisted'}
                          color={user.is_whitelisted ? 'success' : 'default'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={user.is_admin ? 'Admin' : 'User'}
                          color={user.is_admin ? 'primary' : 'default'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        {user.last_login
                          ? new Date(user.last_login).toLocaleDateString()
                          : 'Never'}
                      </TableCell>
                      <TableCell>
                        {user.is_whitelisted && (
                          <IconButton
                            color="error"
                            onClick={() => handleRemoveFromWhitelist(user.email)}
                            size="small"
                          >
                            <DeleteIcon />
                          </IconButton>
                        )}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        {/* Whitelist User Dialog */}
        <Dialog
          open={whitelistDialogOpen}
          onClose={() => setWhitelistDialogOpen(false)}
          maxWidth="sm"
          fullWidth
        >
          <DialogTitle>Whitelist New User</DialogTitle>
          <DialogContent>
            <TextField
              autoFocus
              margin="dense"
              label="Email Address"
              type="email"
              fullWidth
              variant="outlined"
              value={newUserEmail}
              onChange={(e) => setNewUserEmail(e.target.value)}
              sx={{ mb: 2 }}
            />
            <FormControlLabel
              control={
                <Switch
                  checked={newUserIsAdmin}
                  onChange={(e) => setNewUserIsAdmin(e.target.checked)}
                />
              }
              label="Grant Admin Privileges"
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setWhitelistDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleWhitelistUser}
              variant="contained"
              disabled={!newUserEmail.trim()}
            >
              Whitelist User
            </Button>
          </DialogActions>
        </Dialog>
          </Box>
        )}

        {activeTab === 1 && (
          <DomainManagement />
        )}
      </Box>
    </Container>
  );
};

export default Admin;
