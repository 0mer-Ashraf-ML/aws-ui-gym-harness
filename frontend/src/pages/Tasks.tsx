import { Box } from "@mui/material";
import GymList from "../components/GymList";
import type { GymWithTaskCount } from "../types";

function Tasks() {
  const handleSelectGym = (_gym: GymWithTaskCount) => {
    // This will be handled by navigation in GymListCard
  };

  const handleAddTask = (_gym: GymWithTaskCount) => {
    // This will be handled by navigation in GymListCard
  };

  return (
    <Box>
      <GymList
        onSelectGym={handleSelectGym}
        onAddTask={handleAddTask}
      />
    </Box>
  );
}

export default Tasks;
