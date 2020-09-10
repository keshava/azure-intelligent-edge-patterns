import React, { useEffect, useState } from 'react';
import { Link as RRDLink } from 'react-router-dom';
import {
  Stack,
  PrimaryButton,
  ProgressIndicator,
  Text,
  getTheme,
  Separator,
  CommandBar,
  ICommandBarItemProps,
  Pivot,
  PivotItem,
  Link,
  IDropdownOption,
  Dropdown,
  Toggle,
  DefaultButton,
} from '@fluentui/react';
import { useSelector, useDispatch } from 'react-redux';
import * as R from 'ramda';

import { State } from 'RootStateType';
import { LiveViewContainer } from './LiveViewContainer';
import { Project, Status } from '../store/project/projectTypes';
import { useInterval } from '../hooks/useInterval';
import {
  thunkGetTrainingLog,
  thunkGetInferenceMetrics,
  thunkDeleteProject,
  thunkGetTrainingMetrics,
  thunkGetProject,
} from '../store/project/projectActions';
import { ConfigurationInfo } from './ConfigurationInfo/ConfigurationInfo';
import { selectCamerasByIds, selectCameraById } from '../store/cameraSlice';
import { selectPartNamesById } from '../store/partSlice';
import { ConfigTaskPanel } from './ConfigTaskPanel';
import { ExpandPanel } from './ExpandPanel';
import { selectAOIsByCamera, selectOriginAOIsByCamera, onCreateAOIBtnClick } from '../store/AOISlice';
import { toggleShowAOI, updateCameraArea } from '../store/actions';
import { Shape } from '../store/shared/BaseShape';

const { palette } = getTheme();

export const Deployment: React.FC<{ isDemo: boolean }> = ({ isDemo }) => {
  const { status, progress, trainingLog, data: projectData, inferenceMetrics } = useSelector<State, Project>(
    (state) => state.project,
  );
  const {
    id: projectId,
    cameras: projectCameraIds,
    trainingProject,
    parts,
    sendMessageToCloud,
    framesPerMin,
    accuracyThreshold,
    needRetraining,
    accuracyRangeMin,
    accuracyRangeMax,
    maxImages,
    name,
  } = projectData;
  const cameraOptions: IDropdownOption[] = useSelector((state: State) =>
    selectCamerasByIds(projectCameraIds)(state).map((e) => ({ key: e?.id, text: e?.name })),
  );
  const [selectedCamera, setselectedCamera] = useState(null);
  useEffect(() => {
    if (projectCameraIds.length) setselectedCamera(projectCameraIds[0]);
  }, [projectCameraIds]);

  const partNames = useSelector(selectPartNamesById(parts));
  const dispatch = useDispatch();

  const [isEditPanelOpen, setisEditPanelOpen] = useState(false);
  const openPanel = () => setisEditPanelOpen(true);
  const closePanel = () => setisEditPanelOpen(false);

  useEffect(() => {
    dispatch(thunkGetProject());
  }, [dispatch]);

  useInterval(
    () => {
      dispatch(thunkGetTrainingLog(projectId, isDemo));
    },
    status === Status.WaitTraining ? 5000 : null,
  );

  useEffect(() => {
    if (status === Status.FinishTraining) {
      dispatch(thunkGetTrainingMetrics(trainingProject, isDemo));
    }
  }, [dispatch, status, projectId, isDemo, trainingProject]);

  useInterval(
    () => {
      dispatch(thunkGetInferenceMetrics(projectId, isDemo));
    },
    status === Status.StartInference ? 5000 : null,
  );

  const commandBarItems: ICommandBarItemProps[] = [
    {
      key: 'edit',
      text: 'Edit',
      iconProps: {
        iconName: 'Edit',
      },
      onClick: openPanel,
    },
    {
      key: 'delete',
      text: 'Delete',
      iconProps: {
        iconName: 'Delete',
      },
      onClick: () => {
        // Because onClick cannot accept the return type Promise<void>, use the IIFE to workaround
        (async () => {
          // eslint-disable-next-line no-restricted-globals
          if (!confirm('Sure you want to delete?')) return;

          await dispatch(thunkDeleteProject(false));
        })();
      },
    },
  ];

  const onRenderMain = () => {
    if (status === Status.None) return <PrimaryButton onClick={openPanel}>Config Task</PrimaryButton>;
    if (status === Status.WaitTraining)
      return (
        <Stack horizontalAlign="center" verticalAlign="center" grow tokens={{ childrenGap: 24 }}>
          <Stack horizontalAlign="center" tokens={{ childrenGap: 5 }}>
            {progress !== null && (
              <>
                <Text variant="xxLarge">{`${progress}%`}</Text>
                <Text>{trainingLog}</Text>
              </>
            )}
          </Stack>
          <ProgressIndicator
            barHeight={4}
            styles={{ root: { width: '600px' }, progressBar: { backgroundColor: palette.tealLight } }}
            percentComplete={progress !== null ? progress / 100 : null}
          />
        </Stack>
      );

    return (
      <Stack horizontal grow>
        <Stack grow>
          <Stack tokens={{ childrenGap: 17, padding: 25 }} grow>
            <Stack grow>
              <LiveViewContainer showVideo={true} cameraId={selectedCamera} />
            </Stack>
            <Stack horizontal horizontalAlign="space-between">
              <Stack tokens={{ childrenGap: 10 }} styles={{ root: { minWidth: '200px' } }}>
                <Text variant="xLarge">{name}</Text>
                <Text styles={{ root: { color: palette.neutralSecondary } }}>
                  Started running <b>{/* TODO */} ago</b>
                </Text>
                <CommandBar items={commandBarItems} styles={{ root: { padding: 0 } }} />
              </Stack>
              <Dropdown
                options={cameraOptions}
                label="Select Camera"
                styles={{
                  root: { display: 'flex', alignItems: 'flex-start' },
                  dropdown: { width: '180px', marginLeft: '24px' },
                }}
                selectedKey={selectedCamera}
                onChange={(_, option) => setselectedCamera(option.key)}
              />
            </Stack>
          </Stack>
          <Separator styles={{ root: { padding: 0 } }} />
          <Stack tokens={{ childrenGap: 17, padding: 25 }}>
            <ConfigurationInfo
              cameraName={cameraOptions.map((e) => e.text).join(', ')}
              partNames={partNames}
              sendMessageToCloud={sendMessageToCloud}
              framesPerMin={framesPerMin}
              accuracyThreshold={accuracyThreshold}
              needRetraining={needRetraining}
              accuracyRangeMin={accuracyRangeMin}
              accuracyRangeMax={accuracyRangeMax}
              maxImages={maxImages}
            />
          </Stack>
        </Stack>
        <Separator vertical />
        <Stack styles={{ root: { width: '435px' } }}>
          <Pivot styles={{ root: { borderBottom: `solid 1px ${palette.neutralLight}` } }}>
            <PivotItem headerText="Insights">
              <Insights
                successRate={inferenceMetrics.successRate}
                successfulInferences={inferenceMetrics.successfulInferences}
                unIdetifiedItems={inferenceMetrics.unIdetifiedItems}
              />
            </PivotItem>
            <PivotItem headerText="Areas of interest">
              <AOIControls cameraId={selectedCamera} />
            </PivotItem>
          </Pivot>
        </Stack>
      </Stack>
    );
  };

  return (
    <>
      <Stack horizontal styles={{ root: { height: '100%' } }}>
        {onRenderMain()}
      </Stack>
      <ConfigTaskPanel isOpen={isEditPanelOpen} onDismiss={closePanel} projectData={projectData} />
    </>
  );
};

type InsightsProps = {
  successRate: number;
  successfulInferences: number;
  unIdetifiedItems: number;
};

export const Insights: React.FC<InsightsProps> = ({
  successRate,
  successfulInferences,
  unIdetifiedItems,
}) => {
  return (
    <>
      <Stack
        styles={{ root: { padding: '24px 20px', borderBottom: `solid 1px ${palette.neutralLight}` } }}
        tokens={{ childrenGap: '8px' }}
      >
        <Text styles={{ root: { fontWeight: 'bold' } }}>Success rate</Text>
        <Text styles={{ root: { fontWeight: 'bold', color: palette.greenLight } }}>{successRate}%</Text>
      </Stack>
      <Stack
        styles={{ root: { padding: '24px 20px', borderBottom: `solid 1px ${palette.neutralLight}` } }}
        tokens={{ childrenGap: '8px' }}
      >
        <Text styles={{ root: { fontWeight: 'bold' } }}>Successful inferences</Text>
        <Text styles={{ root: { color: palette.neutralSecondary } }}>{successfulInferences}</Text>
        <ExpandPanel titleHidden="Object" suffix={'' /* TODO */} />
        <ExpandPanel titleHidden="Area of interest" suffix={'' /* TODO */} />
      </Stack>
      <Stack
        styles={{ root: { padding: '24px 20px', borderBottom: `solid 1px ${palette.neutralLight}` } }}
        tokens={{ childrenGap: '8px' }}
      >
        <ExpandPanel titleHidden="Unidentified images" suffix={unIdetifiedItems?.toString()}>
          <Stack horizontal tokens={{ childrenGap: 25 }}>
            <Text variant="mediumPlus" styles={{ root: { color: palette.neutralPrimary } }}>
              {unIdetifiedItems} images
            </Text>
            <RRDLink to="/images" style={{ textDecoration: 'none' }}>
              <Link styles={{ root: { textDecoration: 'none' } }}>View in images</Link>
            </RRDLink>
          </Stack>
        </ExpandPanel>
      </Stack>
    </>
  );
};

type AOIControlsProps = {
  cameraId: number;
};

const AOIControls: React.FC<AOIControlsProps> = ({ cameraId }) => {
  const [loading, setLoading] = useState(false);
  const showAOI = useSelector<State, boolean>((state) => selectCameraById(state, cameraId)?.useAOI);
  const AOIs = useSelector(selectAOIsByCamera(cameraId));
  const originAOIs = useSelector(selectOriginAOIsByCamera(cameraId));
  const [showUpdateSuccessTxt, setShowUpdateSuccessTxt] = useState(false);
  const AOIShape = useSelector((state: State) => state.AOIs.shape);
  const dispatch = useDispatch();

  const onCheckboxClick = async (): Promise<void> => {
    setLoading(true);
    try {
      await dispatch(toggleShowAOI({ cameraId, showAOI: !showAOI }));
      setShowUpdateSuccessTxt(true);
    } catch (e) {
      alert(e);
    }
    setLoading(false);
  };

  const onUpdate = async (): Promise<void> => {
    setLoading(true);
    try {
      await dispatch(updateCameraArea(cameraId));
      setShowUpdateSuccessTxt(true);
    } catch (e) {
      alert(e);
    }
    setLoading(false);
  };

  const hasEdit = !R.equals(originAOIs, AOIs);
  const updateBtnDisabled = !showAOI || !hasEdit;

  return (
    <Stack tokens={{ childrenGap: 10 }}>
      <Toggle label="Enable area of interest" checked={showAOI} onClick={onCheckboxClick} inlineLabel />
      <DefaultButton
        text="Create Box"
        primary={AOIShape === Shape.BBox}
        disabled={!showAOI}
        onClick={(): void => {
          dispatch(onCreateAOIBtnClick(Shape.BBox));
        }}
        style={{ padding: '0 5px' }}
      />
      <DefaultButton
        text={AOIShape === Shape.Polygon ? 'Click F to Finish' : 'Create Polygon'}
        primary={AOIShape === Shape.Polygon}
        disabled={!showAOI}
        onClick={(): void => {
          dispatch(onCreateAOIBtnClick(Shape.Polygon));
        }}
        style={{ padding: '0 5px' }}
      />
      <PrimaryButton text="Update" disabled={updateBtnDisabled || loading} onClick={onUpdate} />
      <Text style={{ visibility: showUpdateSuccessTxt ? 'visible' : 'hidden' }}>Updated!</Text>
    </Stack>
  );
};
