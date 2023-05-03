from abc import ABC
from abc import abstractmethod

import torch


class GradScaler(ABC):
    def __init__(self, initial_scale, device=None):
        """Initialize scale value with the input initial scale."""
        assert initial_scale > 0.0
        self.device = device
        self._scale = torch.cuda.FloatTensor([initial_scale], device=device)

    @property
    def scale(self):
        return self._scale

    @property
    def inv_scale(self):
        return self._scale.double().reciprocal().float()

    @abstractmethod
    def update(self, found_inf):
        pass

    @abstractmethod
    def state_dict(self):
        pass

    @abstractmethod
    def load_state_dict(self, state_dict):
        pass


class ConstantGradScaler(GradScaler):

    def update(self, found_inf):
        pass

    def state_dict(self):
        return {}

    def load_state_dict(self, state_dict):
        pass


class DynamicGradScaler(GradScaler):

    def __init__(self, initial_scale, min_scale,
                 growth_factor, backoff_factor,
                 growth_interval, hysteresis, device=None):
        """"Grad scaler with dynamic scale that gets adjusted
        during training."""
        super(DynamicGradScaler, self).__init__(initial_scale, device=device)

        # Lower bound on the scale.
        assert min_scale > 0.0
        assert min_scale <= initial_scale
        self.min_scale = torch.cuda.FloatTensor([min_scale], device=device)
        # Growth and backoff factors for the scale.
        assert growth_factor > 1.0
        self.growth_factor = torch.cuda.FloatTensor([growth_factor], device=device)
        assert backoff_factor < 1.0
        assert backoff_factor > 0.0
        self.backoff_factor = torch.cuda.FloatTensor([backoff_factor], device=device)
        # Interval over which if we don't see any inf/nan,
        # we will scale the grad scale by the growth factor.
        assert growth_interval > 0
        self.growth_interval = growth_interval
        # Number of inf/nans we should see before scaling down
        # the grad scale by the backoff factor.
        assert hysteresis > 0
        self.hysteresis = hysteresis

        # Trackers.
        self._growth_tracker = 0
        self._hysteresis_tracker = self.hysteresis

    def update(self, found_inf):
        # If we have an inf/nan, growth tracker is set to 0
        # and hysterisis tracker is reduced by 1.
        if found_inf:
            self._growth_tracker = 0
            self._hysteresis_tracker -= 1
            # Now if we are out of hysteresis count, scale down the loss.
            if self._hysteresis_tracker <= 0:
                self._scale = torch.max(self._scale * self.backoff_factor,
                                        self.min_scale)
                print('##### scale backoff to', self._scale)
        else:
            # If there is no nan/inf, increment the growth tracker.
            self._growth_tracker += 1
            # If we have had enough consequitive intervals with no nan/inf:
            if self._growth_tracker == self.growth_interval:
                # Reset the tracker and hysteresis trackers,
                self._growth_tracker = 0
                self._hysteresis_tracker = self.hysteresis
                # and scale up the loss scale.
                self._scale = self._scale * self.growth_factor
                print('##### scale grow to', self._scale)

    def state_dict(self):
        return {
            'scale': self._scale,
            'growth_tracker': self._growth_tracker,
            'hysteresis_tracker': self._hysteresis_tracker,
        }

    def load_state_dict(self, state_dict):
        self._scale = state_dict['scale'].to(self.device)
        self._growth_tracker = state_dict['growth_tracker']
        self._hysteresis_tracker = state_dict['hysteresis_tracker']