import json
import datetime
import time
import threading
import queue
import random
import sys
import logging

from django.db import models
from django.db.models.signals import post_save, post_delete, pre_save, post_save, m2m_changed
import cv2
import requests
from io import BytesIO
from PIL import Image as PILImage

from azure.cognitiveservices.vision.customvision.training import CustomVisionTrainingClient
from azure.cognitiveservices.vision.customvision.training.models import ImageFileCreateEntry, Region
from azure.cognitiveservices.vision.customvision.training.models.custom_vision_error_py3 import CustomVisionErrorException
from azure.iot.device import IoTHubModuleClient


from azure.iot.device import IoTHubModuleClient
from vision_on_edge.settings import TRAINING_KEY, ENDPOINT

try:
    iot = IoTHubRegistryManager(IOT_HUB_CONNECTION_STRING)
except:
    iot = None


def is_edge():
    try:
        IoTHubModuleClient.create_from_edge_environment()
        return True
    except:
        return False


logger = logging.getLogger(__name__)


def inference_module_url():
    if is_edge():
        return '172.18.0.1:5000'
    else:
        return 'localhost:5000'


# Create your models here.

class Part(models.Model):
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=1000)
    is_demo = models.BooleanField(default=False)

    class Meta:
        unique_together = ('name', 'is_demo')

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=1000)
    coordinates = models.CharField(max_length=200)
    is_demo = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Image(models.Model):
    image = models.ImageField(upload_to='images/')
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    labels = models.CharField(max_length=1000, null=True)
    is_relabel = models.BooleanField(default=False)
    confidence = models.FloatField(default=0.0)
    uploaded = models.BooleanField(default=False)
    remote_url = models.CharField(max_length=1000, null=True)

    def get_remote_image(self):
        if self.remote_url:
            resp = requests.get(self.remote_url)
            if resp.status_code != requests.codes.ok:
                raise
            fp = BytesIO()
            fp.write(resp.content)
            file_name = f"{self.part.name}-{self.remote_url.split('/')[-1]}"
            logger.info(f"Saving as name {file_name}")
            from django.core import files

            self.image.save(file_name, files.File(fp))
            fp.close()
            self.save()
        else:
            raise

    def set_labels(self, left: float, top: float, width: float, height: float):
        try:
            if left > 1 or top > 1 or width > 1 or height > 1:
                raise ValueError(
                    f"{left}, {top}, {width}, {height} must be less than 1")
            elif left < 0 or top < 0 or width < 0 or height < 0:
                raise ValueError(
                    f"{left}, {top}, {width}, {height} must be greater than 0")
            elif (left + width) > 1 or (top + height) > 1:
                raise ValueError(
                    f"left + width:{left + width}, top + height:{top + height} must be less than 1")
            from PIL import Image
            with Image.open(self.image) as img:
                logger.info(f"Successfully open img {self.image}")
                size_width, size_height = img.size
                label_x1 = int(size_width*left)
                label_y1 = int(size_height*top)
                label_x2 = int(size_width*(left+width))
                label_y2 = int(size_height*(top+height))
                self.labels = json.dumps([{
                    'x1': label_x1,
                    'y1': label_y1,
                    'x2': label_x2,
                    'y2': label_y2}
                ])
                self.save()
                logger.info(f"Successfully save labels to {self.labels}")
        except ValueError:
            logger.exception("Set Annotation: Region Error")
        except:
            logger.exception("Unexpected Error")


class Annotation(models.Model):
    image = models.OneToOneField(Image, on_delete=models.CASCADE)
    labels = models.CharField(max_length=1000, null=True)


class Setting(models.Model):
    """
    A wrapper model of CustomVisionTraingClient.
    Try not to pass CustomVisionTraingClient object if new model is expected to be created.
    e.g. create project, create train/iteration
    Instead, create a wrapper methods and let call, in order to sync the db with remote.
    """
    name = models.CharField(
        max_length=100, blank=True, default='', unique=True)
    endpoint = models.CharField(max_length=1000, blank=True)
    training_key = models.CharField(max_length=1000, blank=True)
    iot_hub_connection_string = models.CharField(max_length=1000, blank=True)
    device_id = models.CharField(max_length=1000, blank=True)
    module_id = models.CharField(max_length=1000, blank=True)

    is_trainer_valid = models.BooleanField(default=False)
    obj_detection_domain_id = models.CharField(
        max_length=1000, blank=True, default='')

    class Meta:
        unique_together = ('endpoint', 'training_key')

    @staticmethod
    def _get_trainer_obj_static(endpoint: str, training_key: str):
        """
        return <CustomVisionTrainingClient>.
        : Success: return CustomVisionTrainingClient object
        """
        try:
            trainer = CustomVisionTrainingClient(
                api_key=training_key, endpoint=endpoint)
            return trainer
        except:
            logger.exception("Unexpected Error")
            return None

    def _get_trainer_obj(self):
        """
        return CustomVisionTrainingClient(self.training_key, self.endpoint)
        : Success: return the CustomVisionTrainingClient object
        """
        return Setting._get_trainer_obj_static(
            endpoint=self.endpoint, training_key=self.training_key)

    def revalidate(self):
        """
        Create a client, try to get obj_detection_domain, return is task success
        Update self.is_trainer_valid and return it's value
        Update obj_detection_domain_id to '' if failed
        : Success: True
        : Failed:  False
        """
        trainer = self._get_trainer_obj()
        try:
            obj_detection_domain = next(domain for domain in trainer.get_domains(
            ) if domain.type == "ObjectDetection" and domain.name == "General (compact)")
            self.is_trainer_valid = True
            self.obj_detection_domain_id = obj_detection_domain.id
            logger.info(
                "Successfully created trainer client and got obj detection domain")
        except:
            # logger.exception('revalidate exception')
            logger.error(
                "Failed to create trainer client or get obj detection domain")
            self.is_trainer_valid = False
            self.obj_detection_domain_id = ''
        logger.info(
            f"{self.name} is_trainer_valid: {self.is_trainer_valid}")
        return self.is_trainer_valid

    def revalidate_and_get_trainer_obj(self):
        """
        Update all the relevent fields and return the CustimVisionClient obj.
        : Success: return CustimVisionClient object
        : Failed:  return None
        """
        if self.revalidate():
            trainer = self._get_trainer_obj()
            return trainer
        else:
            return None

    @staticmethod
    def pre_save(sender, instance, update_fields, **kwargs):
        logger.info("Setting Presave")
        try:
            logger.info(f"instance.id: {instance.id}")
            logger.info(f"update fields: {update_fields}")

            if update_fields is not None:
                return
            logger.info(
                f'Validating Trainer {instance.name} (CustomVisionClient)')

            trainer = Setting._get_trainer_obj_static(
                training_key=instance.training_key,
                endpoint=instance.endpoint)
            obj_detection_domain = next(domain for domain in trainer.get_domains(
            ) if domain.type == "ObjectDetection" and domain.name == "General (compact)")

            logger.info(
                f'Validating Trainer {instance.name} (CustomVisionClient)... Pass')
            instance.is_trainer_valid = True
            instance.obj_detection_domain_id = obj_detection_domain.id
            logger.info("Setting Presave... End")
        except:
            logger.exception(
                "pre_save exception. Set is_trainer_valid to false and obj_detection_domain_id to ''")
            instance.is_trainer_valid = False
            instance.obj_detection_domain_id = ''

    def create_project(self, project_name: str):
        """
        : Success: return project
        : Failed:  return None
        """
        trainer = self.revalidate_and_get_trainer_obj()
        logger.info("Creating obj detection project")
        logger.info(f"trainer: {trainer}")
        if not trainer:
            logger.info("Trainer is invalid thus cannot create project")
            return None
        try:
            project = trainer.create_project(
                name=project_name,
                domain_id=self.obj_detection_domain_id)
            return project
        except:
            logger.exception(
                "Endpoint + Training_Key can create client but cannot create project")
            return None

    def delete_project(self, project_id: str):
        """
        : Success: return project
        : Failed:  return None
        """
        pass

    def __str__(self):
        return self.name


class Camera(models.Model):
    name = models.CharField(max_length=200)
    rtsp = models.CharField(max_length=1000)
    model_name = models.CharField(max_length=200)
    area = models.CharField(max_length=1000, blank=True)
    is_demo = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    @staticmethod
    def post_save(sender, instance, update_fields, **kwargs):
        if len(instance.area) > 1:
            logger.info('Sending new AOI to Inference Module...')
            requests.get('http://'+inference_module_url()+'/update_cam', params={
                         'cam_type': 'rtsp', 'cam_source': instance.rtsp, 'aoi': instance.area})


post_save.connect(Camera.post_save, Camera, dispatch_uid='Camera_post')


class Project(models.Model):
    setting = models.ForeignKey(
        Setting, on_delete=models.CASCADE, default=1)
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    parts = models.ManyToManyField(
        Part, related_name='part')
    customvision_project_id = models.CharField(max_length=200)
    customvision_project_name = models.CharField(max_length=200)
    download_uri = models.CharField(max_length=1000, null=True, blank=True)
    needRetraining = models.BooleanField(default=False)
    accuracyRangeMin = models.IntegerField(null=True)
    accuracyRangeMax = models.IntegerField(null=True)
    maxImages = models.IntegerField(null=True)
    deployed = models.BooleanField(default=False)
    train_try_counter = models.IntegerField(default=0)
    train_success_counter = models.IntegerField(default=0)
    is_demo = models.BooleanField(default=False)

    @staticmethod
    def pre_save(sender, instance, update_fields, **kwargs):
        logger.info("Project pre_save")
        logger.info(f'Saving instance: {instance} {update_fields}')

        if update_fields is not None:
            return
        # if instance.id is not None:
        #    return

        name = 'VisionOnEdge-' + datetime.datetime.utcnow().isoformat()
        instance.customvision_project_name = name

        setting = instance.setting
        instance.setting.revalidate()
        instance.setting.save()
        setting = instance.setting

        if setting.is_trainer_valid and instance.customvision_project_id:
            logger.info(
                f'Updating CustomVision id: {instance.customvision_project_id}')
            logger.info('Assume Syncing')
            try:
                trainer = setting.revalidate_and_get_trainer_obj()
                trainer.get_project(instance.customvision_project_id)
            except:
                logger.exception("Unexpected error")
        elif setting.is_trainer_valid:
            logger.info('Creating Project on Custom Vision')
            project = setting.create_project(name)
            logger.info(f'Got Custom Vision Project Id: {project.id}')
            instance.customvision_project_id = project.id
        else:
            logger.info('Has not set the key, Got DUMMY PRJ ID')
            instance.customvision_project_id = 'DUMMY-PROJECT-ID'
        logger.info("Project pre_save... End")

    @staticmethod
    def post_save(sender, instance, created, update_fields, **kwargs):
        logger.info("Project post_save")
        logger.info(f'Saving instance: {instance} {update_fields}')

        if update_fields is not None:
            return
        if not created:
            logger.info("Project modified")

        project_id = instance.id
        logger.info("Project post_save... End")
        # def _train_f(pid):
        #     requests.get('http://localhost:8000/api/projects/'+str(pid)+'/train')
        # t = threading.Thread(target=_train_f, args=(project_id,))
        # t.start()

    @staticmethod
    def pre_delete(sender, instance, using):
        pass

    def dequeue_iterations(self, max_iterations=2):
        """
        Dequeue training iterations
        """
        try:
            trainer = self.setting.revalidate_and_get_trainer_obj()
            if not trainer:
                return
            iterations = trainer.get_iterations(self.customvision_project_id)
            if len(iterations) > max_iterations:
                # TODO delete train in Train Model
                trainer.delete_iteration(
                    self.customvision_project_id, iterations[-1].as_dict()['id'])
        except:
            logger.exception('dequeue_iteration error')
            return

    def upcreate_training_status(self, status: str, log: str, performance: str = '{}'):
        obj, created = Train.objects.update_or_create(
            project=self,
            defaults={
                'status': status,
                'log': log,
                'performance': performance}
        )
        return obj, created

    def train_project(self):
        """
        Train project self. Return is training request success (boolean)
        counter +=1 
        : Success: return True
        : Failed : return False
        """
        is_task_success = False
        update_fields = []

        try:

            from opencensus.ext.azure.trace_exporter import AzureExporter
            from opencensus.trace.samplers import ProbabilitySampler

            from configs.app_insight import APP_INSIGHT_ON, APP_INSIGHT_INST_KEY, APP_INSIGHT_CONN_STR
            from opencensus.ext.azure.log_exporter import AzureLogHandler

            if APP_INSIGHT_ON:
                logger = logging.getLogger("Backend-Training-App-Insight")
                logger.addHandler(AzureLogHandler(
                    connection_string=APP_INSIGHT_CONN_STR)
                )
            else:
                logger = logging.getLogger(__name__)

            self.train_try_counter += 1
            update_fields.append('train_try_counter')
            logger.info(
                f"Project: {self.customvision_project_name} train attempt count: {self.train_try_counter}")
            trainer = self.setting.revalidate_and_get_trainer_obj()
            if not trainer:
                logger.error('Trainer is invalid. Not going to train...')
                raise

            # Submit training task
            logger.info(
                f"{self.customvision_project_name} submit training task to CustomVision")
            trainer.train_project(self.customvision_project_id)

            # Set trainer_counter
            self.train_success_counter += 1
            update_fields.append('train_success_counter')
            logger.info(
                f"Project: {self.customvision_project_name} train submit count: {self.train_success_counter}")

            # Set deployed
            self.deployed = False
            update_fields.append('deployed')
            logger.info('set deployed = False')

            # If all above is success
            is_task_success = True
        except CustomVisionErrorException as cvee:
            logger.error(
                'From Custom Vision: Nothing changed since last training')
            raise cvee
        except:
            logger.exception('Something wrong while training project')
            raise
        # finally:
        #    self.save(update_fields=update_fields)
        #    return is_task_success

    # @staticmethod
    # def m2m_changed(sender, instance, action, **kwargs):
    #    print('[INFO] M2M_CHANGED')
    #    project_id = instance.id
    #    #print(instance.parts)
    #    requests.get('http://localhost:8000/api/projects/'+str(project_id)+'/train')


class Train(models.Model):
    status = models.CharField(max_length=200)
    log = models.CharField(max_length=1000)
    performance = models.CharField(max_length=1000, default='{}')
    project = models.ForeignKey(Project, on_delete=models.CASCADE)


pre_save.connect(Project.pre_save, Project, dispatch_uid='Project_pre')
post_save.connect(Project.post_save, Project, dispatch_uid='Project_post')
# m2m_changed.connect(Project.m2m_changed, Project.parts.through, dispatch_uid='Project_m2m')
pre_save.connect(Setting.pre_save, Setting, dispatch_uid='Setting_pre')


# FIXME consider move this out of models.py
class Stream(object):
    def __init__(self, rtsp, part_id=None, inference=False):
        if rtsp == '0':
            self.rtsp = 0
        elif rtsp == '1':
            self.rtsp = 1
        else:
            self.rtsp = rtsp
        self.part_id = part_id

        self.last_active = time.time()
        self.status = 'init'
        self.last_img = None
        self.cur_img_index = 0
        self.last_get_img_index = 0
        self.id = id(self)

        self.mutex = threading.Lock()
        self.predictions = []
        self.inference = inference

        try:
            self.iot = IoTHubModuleClient.create_from_edge_environment()
        except:
            self.iot = None

        print('inference', self.inference)
        print('iot', self.iot)

        def _listener(self):
            if not self.inference:
                return
            while True:
                if self.last_active + 10 < time.time():
                    print('[INFO] stream finished')
                    break
                sys.stdout.flush()
                res = requests.get(
                    'http://'+inference_module_url()+'/prediction')

                self.mutex.acquire()
                self.predictions = res.json()
                self.mutex.release()
                time.sleep(0.02)
                # print('received p', self.predictions)

                # inference = self.iot.receive_message_on_input('inference', timeout=1)
                # if not inference:
                #    self.mutex.acquire()
                #    self.bboxes = []
                #    self.mutex.release()
                # else:
                #    data = json.loads(inference.data)
                #    print('receive inference', data)
                #    self.mutex.acquire()
                #    self.bboxes = [{
                #        'label': data['Label'],
                #        'confidence': data['Confidence'] + '%',
                #        'p1': (data['Position'][0], data['Position'][1]),
                #        'p2': (data['Position'][2], data['Position'][3])
                #    }]
                #    self.mutex.release()

        # if self.iot:
        threading.Thread(target=_listener, args=(self,)).start()

    def gen(self):
        self.status = 'running'
        print('[INFO] start streaming with', self.rtsp, flush=True)
        self.cap = cv2.VideoCapture(self.rtsp)
        while self.status == 'running':
            t, img = self.cap.read()
            # Need to add the video flag FIXME
            if t == False:
                print('[INFO] restart cam ...', flush=True)
                self.cap = cv2.VideoCapture(self.rtsp)
                time.sleep(1)
                continue

            img = cv2.resize(img, None, fx=0.5, fy=0.5)
            self.last_active = time.time()
            self.last_img = img.copy()
            self.cur_img_index = (self.cur_img_index + 1) % 10000
            self.mutex.acquire()
            predictions = list(prediction.copy()
                               for prediction in self.predictions)
            self.mutex.release()
            # print('bboxes', bboxes)
            # cv2.rectangle(img, bbox['p1'], bbox['p2'], (0, 0, 255), 3)
            # cv2.putText(img, bbox['label'] + ' ' + bbox['confidence'], (bbox['p1'][0], bbox['p1'][1]-15), cv2.FONT_HERSHEY_COMPLEX, 0.6, (0, 0, 255), 1)
            height, width = img.shape[0], img.shape[1]
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1
            thickness = 3
            for prediction in predictions:
                if prediction['probability'] > 0.25:
                    x1 = int(prediction['boundingBox']['left'] * width)
                    y1 = int(prediction['boundingBox']['top'] * height)
                    x2 = x1 + int(prediction['boundingBox']['width'] * width)
                    y2 = y1 + int(prediction['boundingBox']['height'] * height)
                    img = cv2.rectangle(
                        img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    img = cv2.putText(
                        img, prediction['tagName'], (x1+10, y1+30), font, font_scale, (0, 0, 255), thickness)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + cv2.imencode('.jpg', img)[1].tobytes() + b'\r\n')
        self.cap.release()

    def get_frame(self):
        print('[INFO] get frame', self)
        # b, img = self.cap.read()
        time_begin = time.time()
        while True:
            if time.time() - time_begin > 5:
                break
            if self.last_get_img_index == self.cur_img_index:
                time.sleep(0.01)
            else:
                break
        self.last_get_img_index = self.cur_img_index
        img = self.last_img.copy()
        # if b: return cv2.imencode('.jpg', img)[1].tobytes()
        # else : return None
        return cv2.imencode('.jpg', img)[1].tobytes()

    def close(self):
        self.status = 'stopped'
        logger.info(f'release {self}')
