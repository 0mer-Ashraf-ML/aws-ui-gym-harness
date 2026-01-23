import React, { useState, useEffect } from 'react';
import {
  Box,
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
} from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { domainService } from '../services/domain';
import * as Types from '../types';

const DomainManagement: React.FC = () => {
  const { token, isAdmin } = useAuth();
  const [domains, setDomains] = useState<Types.Domain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [whitelistDialogOpen, setWhitelistDialogOpen] = useState(false);
  const [newDomain, setNewDomain] = useState('');

  useEffect(() => {
    if (isAdmin) {
      loadDomains();
    }
  }, [isAdmin]);

  // Safety check - only admins should access this component
  if (!isAdmin) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <Typography variant="h6" color="error">
          Access Denied
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Administrator privileges required.
        </Typography>
      </Box>
    );
  }

  const loadDomains = async () => {
    if (!token) return;
    
    try {
      setLoading(true);
      setError(null);
      const response = await domainService.getAllDomains(token);
      setDomains(response.domains);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load domains');
    } finally {
      setLoading(false);
    }
  };

  const handleWhitelistDomain = async () => {
    if (!token || !newDomain.trim()) return;
    
    try {
      setError(null);
      await domainService.whitelistDomain(token, newDomain.trim());
      setSuccess(`Domain ${newDomain} whitelisted successfully`);
      setNewDomain('');
      setWhitelistDialogOpen(false);
      loadDomains();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to whitelist domain');
    }
  };

  const handleToggleDomainStatus = async (domainId: string, currentStatus: boolean) => {
    if (!token) return;
    
    try {
      setError(null);
      await domainService.updateDomain(token, domainId, { is_active: !currentStatus });
      setSuccess(`Domain ${currentStatus ? 'deactivated' : 'activated'} successfully`);
      loadDomains();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update domain');
    }
  };

  const handleDeleteDomain = async (domainId: string, domainName: string) => {
    if (!token) return;
    
    if (!window.confirm(`Are you sure you want to delete domain ${domainName}?`)) {
      return;
    }
    
    try {
      setError(null);
      await domainService.deleteDomain(token, domainId);
      setSuccess(`Domain ${domainName} deleted successfully`);
      loadDomains();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete domain');
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="200px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h5" component="h2">
          Domain Management
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setWhitelistDialogOpen(true)}
        >
          Whitelist Domain
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
                <TableCell>Domain</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {domains.map((domain) => (
                <TableRow key={domain.uuid}>
                  <TableCell>
                    <Typography variant="body2" fontWeight="medium">
                      {domain.domain}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={domain.is_active ? 'Active' : 'Inactive'}
                      color={domain.is_active ? 'success' : 'default'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {new Date(domain.created_at).toLocaleDateString()}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={domain.is_active}
                            onChange={() => handleToggleDomainStatus(domain.uuid, domain.is_active)}
                            size="small"
                          />
                        }
                        label=""
                      />
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleDeleteDomain(domain.uuid, domain.domain)}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
              {domains.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} align="center">
                    <Typography variant="body2" color="text.secondary">
                      No domains found
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {/* Whitelist Domain Dialog */}
      <Dialog
        open={whitelistDialogOpen}
        onClose={() => setWhitelistDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Whitelist New Domain</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Domain Name"
            placeholder="example.com"
            fullWidth
            variant="outlined"
            value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)}
            sx={{ mb: 2 }}
            helperText="Enter the domain name (e.g., example.com). All users with emails from this domain will be able to login."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWhitelistDialogOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleWhitelistDomain}
            variant="contained"
            disabled={!newDomain.trim()}
          >
            Whitelist Domain
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DomainManagement;
